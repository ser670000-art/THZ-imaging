from xmlrpc.server import SimpleXMLRPCServer
from socketserver import ThreadingMixIn
import ctypes
import time
import nidaqmx
from nidaqmx.constants import TerminalConfiguration, AcquisitionType
import atexit
import json
import os
import logging

# =====================================================================
# 📝 模块 0：专业日志配置 (取代 print，方便排查长期实验故障)
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("server_hardware.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("HardwareServer")

logger.info("======================================================")
logger.info("  🚀 1ms 高频轮询驱动服务 - DAQ加速版")
logger.info("======================================================")

CONFIG_FILE = "scan_config.json"

# =====================================================================
# ⚙️ 模块 1：读取 JSON 动态配置
# =====================================================================
def get_motor_dynamics():
    """实时读取 JSON 中的电机动力学参数，避免每次重启服务器"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                cfg = json.load(f)
                mot = cfg.get("hardware_motor", {})
                return {
                    "v_start": int(mot.get("v_start_pulses", 100)), 
                    "acc": int(mot.get("acc_pulses", 5000)),        
                    "dec": int(mot.get("dec_pulses", 5000))         
                }
    except Exception as e:
        logger.warning(f"读取配置失败，使用保守参数: {e}")
    
    return {"v_start": 50, "acc": 2000, "dec": 2000}

# =====================================================================
# ⚡ 模块 2：破解 Windows 15.6ms 睡眠诅咒
# =====================================================================
try:
    winmm = ctypes.windll.winmm
    winmm.timeBeginPeriod(1)
    def restore_windows_timer():
        winmm.timeEndPeriod(1)
    atexit.register(restore_windows_timer)
    logger.info("[内核提速] 已成功将 Windows 线程调度精度提至 1 毫秒！")
except Exception as e:
    logger.error(f"[内核提速失败] 无法调用 winmm.dll: {e}")

class ThreadedXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True

# =====================================================================
# 🔌 模块 3：硬件 DLL 驱动抽象层 (HAL)
# =====================================================================
try:
    mt_api = ctypes.windll.LoadLibrary("./MT_API.dll")
    mt_api.MT_Init()
    mt_api.MT_Open_USB()
    
    mt_api.MT_Set_Axis_Mode_Position.argtypes = [ctypes.c_uint16]
    mt_api.MT_Set_Axis_Position_V_Start.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_V_Max.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_Acc.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_Dec.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_P_Target_Rel.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_P_Target_Abs.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_P_Now.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Get_Axis_P_Now.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_int32)]
    mt_api.MT_Get_Axis_Status_Run.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_int32)]
    mt_api.MT_Get_Axis_Status_Run.restype = ctypes.c_int32
    mt_api.MT_Set_Axis_Halt_All.argtypes = []
    mt_api.MT_Set_Axis_Halt_All.restype = ctypes.c_int32

    logger.info("[驱动加载] 滑台 DLL 驱动与内存指针映射成功。")
except Exception as e:
    logger.error(f"[驱动加载失败] 请检查 USB 连接或 DLL 路径: {e}")

# =====================================================================
# 🛡️ 模块 4：全局状态与安全锁机制
# =====================================================================
GLOBAL_STOP = False

def emergency_stop():
    global GLOBAL_STOP
    GLOBAL_STOP = True
    logger.warning("急停锁死驱动器！")
    try: mt_api.MT_Set_Axis_Halt_All() 
    except: pass
    return True

def reset_stop():
    global GLOBAL_STOP
    GLOBAL_STOP = False
    return True

def set_absolute_zero():
    try:
        for axis in [0, 1, 2]: mt_api.MT_Set_Axis_P_Now(axis, 0)
        logger.info("机械位置已设为绝对空间原点 (0,0,0)")
        return True
    except: return False

# =====================================================================
# ⚙️ 模块 5：闭环运动控制引擎
# =====================================================================
def _wait_for_motion_complete(axis, axis_name, expected_time):
    timeout_limit = expected_time * 1.5 + 2.0  
    start_time = time.perf_counter()  
    pRun = ctypes.c_int32(1) 
    
    while True:
        if GLOBAL_STOP: return False
            
        mt_api.MT_Get_Axis_Status_Run(axis, ctypes.byref(pRun))
        if pRun.value == 0: return True
            
        if time.perf_counter() - start_time > timeout_limit:
            logger.error(f"[致命错误] {axis_name} 轴运动超时！")
            emergency_stop() 
            return False
            
        time.sleep(0.001) 

def _setup_axis_speed(axis, speed_pulses):
    dynamics = get_motor_dynamics()
    mt_api.MT_Set_Axis_Mode_Position(axis)
    mt_api.MT_Set_Axis_Position_V_Start(axis, dynamics['v_start']) 
    mt_api.MT_Set_Axis_Position_V_Max(axis, speed_pulses)
    mt_api.MT_Set_Axis_Position_Acc(axis, dynamics['acc'])   
    mt_api.MT_Set_Axis_Position_Dec(axis, dynamics['dec'])   

def move_mm(axis_name, distance_mm, speed_mm_s, k_ratio):
    global GLOBAL_STOP
    if GLOBAL_STOP or speed_mm_s <= 0: return False

    axis = {'X': 0, 'Y': 1, 'Z': 2}.get(axis_name.upper(), 0)
    pulses = int(distance_mm * k_ratio)
    
    _setup_axis_speed(axis, int(speed_mm_s * k_ratio))
    mt_api.MT_Set_Axis_Position_P_Target_Rel(axis, pulses)
    
    expected_time = abs(distance_mm) / speed_mm_s
    return _wait_for_motion_complete(axis, axis_name, expected_time)

def move_abs_mm(axis_name, target_mm, speed_mm_s, k_ratio):
    global GLOBAL_STOP
    if GLOBAL_STOP or speed_mm_s <= 0: return False

    axis = {'X': 0, 'Y': 1, 'Z': 2}.get(axis_name.upper(), 0)
    target_pulses = int(target_mm * k_ratio)
    
    p_now = ctypes.c_int32(0)
    mt_api.MT_Get_Axis_P_Now(axis, ctypes.byref(p_now))
    distance_pulses = abs(target_pulses - p_now.value)
    
    _setup_axis_speed(axis, int(speed_mm_s * k_ratio))
    mt_api.MT_Set_Axis_Position_P_Target_Abs(axis, target_pulses)
    
    expected_time = (distance_pulses / k_ratio) / speed_mm_s if distance_pulses > 0 else 0
    return _wait_for_motion_complete(axis, axis_name, expected_time)

# =====================================================================
# 📡 模块 6：数据采集引擎 (DAQ) - [核心重构：资源池化]
# =====================================================================
_daq_task = None
_current_daq_config = {}

def cleanup_daq():
    """退出程序时安全释放采集卡资源"""
    global _daq_task
    if _daq_task:
        try:
            _daq_task.close()
            logger.info("DAQ 资源已安全释放。")
        except: pass

atexit.register(cleanup_daq)

def read_thz_raw(samples, rate, v_min, v_max):
    global GLOBAL_STOP, _daq_task, _current_daq_config
    if GLOBAL_STOP: 
        raise Exception("硬件已处于急停状态，拒绝采集")
    
    try:
        # 如果是第一次运行，或者底层采样率/量程发生了变化，才重新分配硬件资源
        needs_reinit = (
            _daq_task is None or 
            _current_daq_config.get('rate') != rate or 
            _current_daq_config.get('v_min') != v_min or
            _current_daq_config.get('v_max') != v_max
        )
        
        if needs_reinit:
            if _daq_task: _daq_task.close()
            _daq_task = nidaqmx.Task()
            _daq_task.ai_channels.add_ai_voltage_chan(
                "Dev1/ai1", 
                terminal_config=TerminalConfiguration.RSE, 
                min_val=v_min, 
                max_val=v_max
            )
            _daq_task.timing.cfg_samp_clk_timing(
                rate=rate, 
                sample_mode=AcquisitionType.FINITE, 
                samps_per_chan=samples
            )
            _current_daq_config = {'rate': rate, 'v_min': v_min, 'v_max': v_max, 'samples': samples}
            
        # 如果仅仅是读取点数变化，不用重建通道，只要改时钟配置即可
        elif _current_daq_config.get('samples') != samples:
            _daq_task.timing.cfg_samp_clk_timing(
                rate=rate, 
                sample_mode=AcquisitionType.FINITE, 
                samps_per_chan=samples
            )
            _current_daq_config['samples'] = samples

        # 🚀 极致轮询：只要复用上面建好的通道 start -> read -> stop 即可
        _daq_task.start()
        data = _daq_task.read(number_of_samples_per_channel=samples)
        _daq_task.stop()
        
        return [float(v) for v in data] 
        
    except Exception as e:
        logger.error(f"[DAQ 采集故障] {e}")
        # 若出现锁死，销毁句柄强制下次重置
        if _daq_task:
            _daq_task.close()
            _daq_task = None
        return [-999.0] * samples

if __name__ == "__main__":
    server = ThreadedXMLRPCServer(("127.0.0.1", 8000), allow_none=True, logRequests=False)
    
    server.register_function(move_mm, "move_mm")
    server.register_function(move_abs_mm, "move_abs_mm")
    server.register_function(set_absolute_zero, "set_absolute_zero")
    server.register_function(read_thz_raw, "read_raw")
    server.register_function(emergency_stop, "emergency_stop")
    server.register_function(reset_stop, "reset_stop")

    logger.info("🔌 多线程 XML-RPC 服务已在 8000 端口启动。")
    logger.info("------------------------------------------------------")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已手动终止。")
from xmlrpc.server import SimpleXMLRPCServer
from socketserver import ThreadingMixIn
import ctypes
import time
import nidaqmx
from nidaqmx.constants import TerminalConfiguration, AcquisitionType
import numpy as np
import atexit
import json
import os
import logging

# =====================================================================
# 📝 模块 0：专业日志配置
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
logger.info("  🚀 边缘计算驱动服务 - 高频飞点加速版")
logger.info("======================================================")

CONFIG_FILE = "scan_config.json"

# =====================================================================
# ⚙️ 模块 1：读取 JSON 动态配置
# =====================================================================
def get_motor_dynamics():
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
# ⚙️ 模块 5：闭环运动控制引擎 (保持不变)
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
# 📡 模块 6：数据采集引擎 (DAQ) - [引入 NumPy 边缘计算]
# =====================================================================
_daq_task = None
_current_daq_config = {}

def cleanup_daq():
    global _daq_task
    if _daq_task:
        try:
            _daq_task.close()
            logger.info("DAQ 资源已安全释放。")
        except: pass

atexit.register(cleanup_daq)

def _init_or_update_daq(samples, rate, v_min, v_max):
    """内部辅助函数：管理 NI Task 句柄，避免重复开关"""
    global _daq_task, _current_daq_config
    
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
            "Dev1/ai1", # 如果你的卡是 ai0，记得在这里改！
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
        
    elif _current_daq_config.get('samples') != samples:
        _daq_task.timing.cfg_samp_clk_timing(
            rate=rate, 
            sample_mode=AcquisitionType.FINITE, 
            samps_per_chan=samples
        )
        _current_daq_config['samples'] = samples

def read_raw(samples, rate, v_min, v_max):
    """【兼容老接口】：纯粹读回一维数组 (用于对焦或单点测试)"""
    global GLOBAL_STOP, _daq_task
    if GLOBAL_STOP: raise Exception("硬件已处于急停状态，拒绝采集")
    
    try:
        _init_or_update_daq(samples, rate, v_min, v_max)
        _daq_task.start()
        data = _daq_task.read(number_of_samples_per_channel=samples)
        _daq_task.stop()
        return [float(v) for v in data] 
    except Exception as e:
        logger.error(f"[DAQ 采集故障] {e}")
        if _daq_task: _daq_task.close(); _daq_task = None
        return [-999.0] * samples

def read_thz_line_binned(total_samples, rate, v_min, v_max, num_pixels):
    """
    🔥 【边缘计算核心】：给飞点扫描专用的降维接口
    直接在服务器端将海量数据切片并求平均，只通过网络传回极小的像素数组！
    """
    global GLOBAL_STOP, _daq_task
    if GLOBAL_STOP: raise Exception("硬件已处于急停状态，拒绝采集")
    
    try:
        _init_or_update_daq(total_samples, rate, v_min, v_max)
        
        # 1. 抓取海量底层数据
        _daq_task.start()
        data = _daq_task.read(number_of_samples_per_channel=total_samples, timeout=20.0)
        _daq_task.stop()
        
        # 2. 🚀 在这里运用 NumPy 进行服务器端降维打击！
        # 例如：传进来 100,000 个点，num_pixels=100
        data_np = np.array(data)
        
        # 计算每个像素能分到多少个采样点
        samples_per_pixel = total_samples // num_pixels
        valid_length = num_pixels * samples_per_pixel
        
        # 规整并切块
        data_np = data_np[:valid_length]
        pixel_blocks = data_np.reshape(num_pixels, samples_per_pixel)
        
        # 针对每个块求平均，瞬间将噪声抹平
        line_pixels = np.mean(pixel_blocks, axis=1)
        
        # 3. 只通过网络返回这 100 个极其干净的数字
        return [float(v) for v in line_pixels]
        
    except Exception as e:
        logger.error(f"[DAQ 边缘计算故障] {e}")
        if _daq_task: _daq_task.close(); _daq_task = None
        return [-999.0] * num_pixels

if __name__ == "__main__":
    server = ThreadedXMLRPCServer(("127.0.0.1", 8000), allow_none=True, logRequests=False)
    
    server.register_function(move_mm, "move_mm")
    server.register_function(move_abs_mm, "move_abs_mm")
    server.register_function(set_absolute_zero, "set_absolute_zero")
    
    # 注册两套 DAQ 接口
    server.register_function(read_raw, "read_raw") 
    server.register_function(read_thz_line_binned, "read_thz_line_binned") # 飞点极速专用
    
    server.register_function(emergency_stop, "emergency_stop")
    server.register_function(reset_stop, "reset_stop")

    logger.info("🔌 多线程 XML-RPC 服务已在 8000 端口启动。")
    logger.info("------------------------------------------------------")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已手动终止。")
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

# 💥 引入你的专业信号处理器
from signal_processor import THzSignalProcessor

# 全局初始化 DSP 引擎
dsp_engine = THzSignalProcessor()

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
logger.info("  🚀 边缘计算融合滤波 (Fused DSP) + 官方 Stream 旗舰版")
logger.info("======================================================")

CONFIG_FILE = "scan_config.json"

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
    except Exception: pass
    return {"v_start": 50, "acc": 2000, "dec": 2000}

try:
    winmm = ctypes.windll.winmm
    winmm.timeBeginPeriod(1)
    atexit.register(lambda: winmm.timeEndPeriod(1))
except Exception: pass

class ThreadedXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    daemon_threads = True

# =====================================================================
# 🔌 模块 3：官方 MT_API.h 精确驱动抽象层 (HAL)
# =====================================================================
try:
    mt_api = ctypes.windll.LoadLibrary("./MT_API.dll")
    mt_api.MT_Init()
    mt_api.MT_Open_USB()
    
    # --- 点到点基础 API ---
    mt_api.MT_Set_Axis_Mode_Position.argtypes = [ctypes.c_uint16]
    mt_api.MT_Set_Axis_Position_V_Max.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_P_Target_Rel.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Axis_Position_P_Target_Abs.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Get_Axis_P_Now.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_int32)]
    mt_api.MT_Get_Axis_Status_Run.argtypes = [ctypes.c_uint16, ctypes.POINTER(ctypes.c_int32)]
    mt_api.MT_Set_Axis_Halt_All.restype = ctypes.c_int32

    # --- 🌟 基于 MT_API.h 官方定义的 Stream 流模式精确映射 ---
    mt_api.MT_Set_Stream_Clear.argtypes = []
    mt_api.MT_Set_Stream_Run.argtypes = []
    mt_api.MT_Set_Stream_Run.restype = ctypes.c_int32
    
    mt_api.MT_Set_Stream_Line_V_Max.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Stream_Circle_V_Max.argtypes = [ctypes.c_uint16, ctypes.c_int32]
    mt_api.MT_Set_Stream_Circle_Axis.argtypes = [ctypes.c_uint16, ctypes.c_int32, ctypes.c_int32]
    
    mt_api.MT_Set_Stream_Line_X_Run_Rel.argtypes = [
        ctypes.c_uint16, ctypes.c_int32, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)
    ]
    mt_api.MT_Set_Stream_Circle_R_CW_Run_Rel.argtypes = [ctypes.c_uint16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]
    mt_api.MT_Set_Stream_Circle_R_CCW_Run_Rel.argtypes = [ctypes.c_uint16, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32]

    logger.info("[驱动加载] ✅ 基于 MT_API.h 的 C++ 内存指针对齐校验完成。")
except Exception as e:
    logger.error(f"[驱动加载失败] {e}")

GLOBAL_STOP = False

def emergency_stop():
    global GLOBAL_STOP
    GLOBAL_STOP = True
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
        return True
    except: return False

def _wait_for_motion_complete(axis, axis_name, expected_time):
    timeout_limit = expected_time * 1.5 + 2.0  
    start_time = time.perf_counter()  
    pRun = ctypes.c_int32(1) 
    while True:
        if GLOBAL_STOP: return False
        mt_api.MT_Get_Axis_Status_Run(axis, ctypes.byref(pRun))
        if pRun.value == 0: return True
        if time.perf_counter() - start_time > timeout_limit:
            emergency_stop(); return False
        time.sleep(0.001) 

def move_mm(axis_name, distance_mm, speed_mm_s, k_ratio):
    global GLOBAL_STOP
    if GLOBAL_STOP or speed_mm_s <= 0: return False
    axis = {'X': 0, 'Y': 1, 'Z': 2}.get(axis_name.upper(), 0)
    mt_api.MT_Set_Axis_Mode_Position(axis)
    mt_api.MT_Set_Axis_Position_V_Max(axis, int(speed_mm_s * k_ratio))
    mt_api.MT_Set_Axis_Position_P_Target_Rel(axis, int(distance_mm * k_ratio))
    return _wait_for_motion_complete(axis, axis_name, abs(distance_mm) / speed_mm_s)

def move_abs_mm(axis_name, target_mm, speed_mm_s, k_ratio):
    global GLOBAL_STOP
    if GLOBAL_STOP or speed_mm_s <= 0: return False
    axis = {'X': 0, 'Y': 1, 'Z': 2}.get(axis_name.upper(), 0)
    mt_api.MT_Set_Axis_Mode_Position(axis)
    mt_api.MT_Set_Axis_Position_V_Max(axis, int(speed_mm_s * k_ratio))
    mt_api.MT_Set_Axis_Position_P_Target_Abs(axis, int(target_mm * k_ratio))
    return _wait_for_motion_complete(axis, axis_name, 5.0)

# =====================================================================
# 🎢 连续流空跑测试 (Stream Mode)
# =====================================================================
def test_smooth_snake_trajectory(x_length_mm, y_step_mm, lines, speed_mm_s, k_ratio):
    global GLOBAL_STOP
    if GLOBAL_STOP: return False

    logger.info("======================================================")
    logger.info(f" 🎢 官方流模式 (Stream) 空跑测试：扫 {lines} 行，无缝过弯掉头")
    logger.info("======================================================")

    try:
        axis_x, axis_y = 0, 1
        group_id = 0  
        
        speed_pulses = int(speed_mm_s * k_ratio)
        x_dist_pulses = int(x_length_mm * k_ratio)
        y_step_pulses = int(y_step_mm * k_ratio)
        radius_pulses = int((y_step_mm / 2.0) * k_ratio)

        mt_api.MT_Set_Stream_Clear()
        mt_api.MT_Set_Stream_Line_V_Max(group_id, speed_pulses)
        mt_api.MT_Set_Stream_Circle_V_Max(group_id, speed_pulses)
        mt_api.MT_Set_Stream_Circle_Axis(group_id, axis_x, axis_y)

        current_x_dir = 1
        for i in range(lines):
            dist_x = x_dist_pulses * current_x_dir
            pAxis = (ctypes.c_int32 * 1)(axis_x)     
            pTarget = (ctypes.c_int32 * 1)(dist_x)   
            mt_api.MT_Set_Stream_Line_X_Run_Rel(group_id, 1, pAxis, pTarget)
            logger.info(f" ➔ 装填 [直线]：轴{axis_x} 走 {dist_x} 脉冲")

            if i < lines - 1:
                if current_x_dir == 1:
                    mt_api.MT_Set_Stream_Circle_R_CW_Run_Rel(group_id, radius_pulses, 0, y_step_pulses)
                    logger.info(f" ➔ 装填 [圆弧]：顺时针过弯")
                else:
                    mt_api.MT_Set_Stream_Circle_R_CCW_Run_Rel(group_id, radius_pulses, 0, y_step_pulses)
                    logger.info(f" ➔ 装填 [圆弧]：逆时针过弯")
            current_x_dir *= -1

        logger.info("🚀 数据装填完毕，硬件连续流启动！脱离电脑控制狂飙！")
        res = mt_api.MT_Set_Stream_Run()
        
        if res != 0:
            logger.error(f"启动数据流失败，板卡返回错误码: {res}")
            return False
        
        total_dist = (x_length_mm * lines) + (y_step_mm * 1.57 * (lines - 1))
        _wait_for_motion_complete(axis_x, "X(流模式)", total_dist / speed_mm_s)
        
        logger.info("✅ 测试圆满完成，机床完美停稳。")
        return True

    except Exception as e:
        logger.error(f"[流模式测试失败] {e}")
        emergency_stop()
        return False

# =====================================================================
# 📡 模块 6：数据采集引擎 (DAQ) 融合计算 (Fused Edge Computing)
# =====================================================================
_daq_task = None
_current_daq_config = {}

def cleanup_daq():
    global _daq_task
    if _daq_task:
        try: _daq_task.close(); logger.info("DAQ 释放。")
        except: pass

atexit.register(cleanup_daq)

def _init_or_update_daq(samples, rate, v_min, v_max):
    global _daq_task, _current_daq_config
    needs_reinit = (_daq_task is None or _current_daq_config.get('rate') != rate)
    if needs_reinit:
        if _daq_task: _daq_task.close()
        _daq_task = nidaqmx.Task()
        _daq_task.ai_channels.add_ai_voltage_chan("Dev1/ai1", terminal_config=TerminalConfiguration.RSE, min_val=v_min, max_val=v_max)
        _daq_task.timing.cfg_samp_clk_timing(rate=rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=samples)
        _current_daq_config = {'rate': rate, 'v_min': v_min, 'v_max': v_max, 'samples': samples}
    elif _current_daq_config.get('samples') != samples:
        _daq_task.timing.cfg_samp_clk_timing(rate=rate, sample_mode=AcquisitionType.FINITE, samps_per_chan=samples)
        _current_daq_config['samples'] = samples

def read_raw(samples, rate, v_min, v_max):
    """用于对焦与实时监控的无损原始读取"""
    global GLOBAL_STOP, _daq_task
    if GLOBAL_STOP: raise Exception("急停态")
    try:
        _init_or_update_daq(samples, rate, v_min, v_max)
        _daq_task.start(); data = _daq_task.read(number_of_samples_per_channel=samples); _daq_task.stop()
        return [float(v) for v in data] 
    except Exception as e:
        if _daq_task: _daq_task.close(); _daq_task = None
        return [-999.0] * samples

def read_thz_line_fused(total_samples, rate, v_min, v_max, num_pixels):
    """🔥 极速飞点融合计算：底层盲采 + 就地滤波降维"""
    global GLOBAL_STOP, _daq_task
    if GLOBAL_STOP: raise Exception("急停态")
    
    try:
        _init_or_update_daq(total_samples, rate, v_min, v_max)
        
        # 1. 抓取海量数据
        _daq_task.start()
        data = _daq_task.read(number_of_samples_per_channel=total_samples, timeout=20.0)
        _daq_task.stop()
        
        # 2. 切片
        data_np = np.array(data)
        samples_per_pixel = total_samples // num_pixels
        pixel_blocks = data_np[:num_pixels * samples_per_pixel].reshape(num_pixels, samples_per_pixel)
        
        raw_means = []
        proc_means = []
        
        # 3. 💥 就地应用你的专属滤波算法
        for i in range(num_pixels):
            r_mean, p_mean, _ = dsp_engine.process_pixel(pixel_blocks[i])
            raw_means.append(float(r_mean))
            proc_means.append(float(p_mean))
            
        # 4. 只通过网络返回两组超浓缩的核心像素阵列！
        return [raw_means, proc_means]
        
    except Exception as e:
        logger.error(f"[DAQ 融合计算故障] {e}")
        if _daq_task: _daq_task.close(); _daq_task = None
        # 抛出特殊的占位符，通知客户端失败
        return [[-999.0]*num_pixels, [-999.0]*num_pixels]

if __name__ == "__main__":
    server = ThreadedXMLRPCServer(("127.0.0.1", 8000), allow_none=True, logRequests=False)
    server.register_function(move_mm, "move_mm")
    server.register_function(move_abs_mm, "move_abs_mm")
    server.register_function(set_absolute_zero, "set_absolute_zero")
    
    server.register_function(read_raw, "read_raw") 
    server.register_function(read_thz_line_fused, "read_thz_line_fused") # 👈 飞点融合极速版
    
    server.register_function(emergency_stop, "emergency_stop")
    server.register_function(reset_stop, "reset_stop")
    server.register_function(test_smooth_snake_trajectory, "test_smooth_snake_trajectory")

    logger.info("🔌 多线程 XML-RPC 服务已在 8000 端口启动。")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
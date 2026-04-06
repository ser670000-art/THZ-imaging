import os
import json
import time
import threading
import xmlrpc.client
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from data_manager import THzDataManager
from signal_processor import THzSignalProcessor

CONFIG_FILE = "scan_config.json"
X_AXIS_POLARITY = 1  
Y_AXIS_POLARITY = 1
Z_AXIS_POLARITY = 1

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: 
                cfg = json.load(f)
                
                # 自动补全缺失的模块配置 (向后兼容)
                if "auto_focus" not in cfg:
                    cfg["auto_focus"] = {"search_range_mm": 10.0, "step_mm": 0.5, "speed_mm_s": 2.0, "wait_time_s": 0.2}
                if "delays_s" not in cfg:
                    cfg["delays_s"] = {"layer": 0.5, "line": 0.2, "pixel": 0.08}
                    
                return cfg
        except Exception as e: 
            print(f"⚠️ JSON读取失败: {e}")
            
    # 全量默认配置字典
    return {
        "project_info": {"sample_name": "3D_Scan_Final"}, 
        "scan_params": {"x_steps": 10, "y_steps": 10, "z_steps": 1, "step_mm": 1.0, "z_step_mm": 0.2, "speed_mm_s": 5.0}, 
        "hardware_daq": {"samples_per_pixel": 1000, "sampling_rate_hz": 10000.0, "volt_min": -1.2, "volt_max": 0.2}, 
        "hardware_motor": {"pulse_ratio_k": 22.13},
        "auto_focus": {"search_range_mm": 10.0, "step_mm": 0.5, "speed_mm_s": 2.0, "wait_time_s": 0.2},
        "delays_s": {"layer": 0.5, "line": 0.2, "pixel": 0.08} 
    }

def save_config(cfg_dict):
    with open(CONFIG_FILE, 'w') as f: 
        json.dump(cfg_dict, f, indent=4)

# ==========================================
# 🚚 手动移动控制线程 (保持不变)
# ==========================================
class MoveThread(QThread):
    finished_signal = pyqtSignal()
    status_signal = pyqtSignal(str)

    def __init__(self, x, y, z, speed, k_ratio):
        super().__init__()
        self.x, self.y, self.z = x, y, z
        self.speed = speed
        self.k_ratio = k_ratio
        self._is_running = True

    def stop(self): self._is_running = False

    def run(self):
        target_x, target_y, target_z = float(self.x * X_AXIS_POLARITY), float(self.y * Y_AXIS_POLARITY), float(self.z * Z_AXIS_POLARITY)
        
        self.status_signal.emit(f"🚚 移动中: 前往坐标 (X:{target_x:.2f}, Y:{target_y:.2f})")
        try:
            hw = xmlrpc.client.ServerProxy("http://127.0.0.1:8000/")
            hw.reset_stop()
            if self._is_running: hw.move_abs_mm('Z', target_z, float(self.speed), float(self.k_ratio))
            if self._is_running: hw.move_abs_mm('X', target_x, float(self.speed), float(self.k_ratio))
            if self._is_running: hw.move_abs_mm('Y', target_y, float(self.speed), float(self.k_ratio))
            if self._is_running: self.status_signal.emit(f"✅ 已精准到达坐标: ({self.x}, {self.y}, {self.z})")
        except Exception as e:
            self.status_signal.emit(f"❌ 移动通信失败: {e}")
        self.finished_signal.emit()

# ==========================================
# 🚀 3D 高速连续飞点扫描引擎 (融合计算极速版)
# ==========================================
class ScanThread(QThread):
    # 完美兼容原 UI 接口：发射单个像素数据
    update_signal = pyqtSignal(int, int, int, object, object, float, float) 
    finished_signal = pyqtSignal()
    status_signal = pyqtSignal(str)
    file_created_signal = pyqtSignal(str) 

    def __init__(self, cfg, target_layers=None, patch_file=None):
        super().__init__()
        self.cfg = cfg
        self._is_running = True
        # 保留 processor 主要是为了兼容寻峰对焦复用，扫描阶段直接用底层算好的结果
        self.processor = THzSignalProcessor() 
        self.target_layers = target_layers
        self.patch_file = patch_file
        self._pause_event = threading.Event()
        self._pause_event.set()

    def pause_scan(self): self._pause_event.clear()
    def resume_scan(self): self._pause_event.set()
    def stop(self): 
        self._is_running = False
        self._pause_event.set() 

    def run(self):
        sp = self.cfg['scan_params']
        daq = self.cfg['hardware_daq']
        mot = self.cfg['hardware_motor']
        prj = self.cfg['project_info']
        delays = self.cfg.get('delays_s', {"layer": 0.5, "line": 0.2, "pixel": 0.08})
        
        # ==========================================
        # 🧮 飞点核心物理与定时计算
        # ==========================================
        speed = float(sp['speed_mm_s'])
        k = float(mot['pulse_ratio_k'])
        
        line_length_mm = (sp['x_steps'] - 1) * sp['step_mm']
        time_per_pixel = sp['step_mm'] / speed
        
        # 根据物理速度，反推 DAQ 卡需要的采样率
        rate_hz = float(daq['samples_per_pixel'] / time_per_pixel)
        total_samples_per_line = int(sp['x_steps'] * daq['samples_per_pixel'])
        
        # 加速缓冲段 (保证滑过扫描区时是绝对匀速，最短2mm)
        overshoot_mm = max(2.0, sp['step_mm'] * 1.5)
        time_to_reach_zero = overshoot_mm / speed

        # 1. 连接下位机控制板
        try:
            hw = xmlrpc.client.ServerProxy("http://127.0.0.1:8000/")
            hw.reset_stop() 
        except Exception as e:
            self.status_signal.emit(f"❌ 硬件连接失败: {e}")
            self.finished_signal.emit()
            return
            
        # 2. 初始化数据存储 (HDF5)
        try:
            db = THzDataManager(prj['sample_name'], sp['x_steps'], sp['y_steps'], sp['z_steps'], sp['step_mm'], daq['samples_per_pixel'], existing_file=self.patch_file)
            self.file_created_signal.emit(db.h5_path) 
        except Exception as e:
            self.status_signal.emit(f"❌ 建立存储文件失败: {e}")
            self.finished_signal.emit()
            return
        
        network_fault = False 
        error_msg = "" 
        z_range = self.target_layers if self.target_layers is not None else range(sp['z_steps'])
        
        global_line_counter = 0

        # 🎯 护航开始
        try:
            for z_idx in z_range:
                if not self._is_running or network_fault: break
                self.status_signal.emit(f"🔴 第 {z_idx+1}/{sp['z_steps']} 层扫描中 (🚀 高频连续飞点模式)...")

                # ==== Z 轴换层 ====
                try:
                    target_z = float(z_idx * sp['z_step_mm'] * Z_AXIS_POLARITY)
                    hw.move_abs_mm('Z', target_z, speed, k)
                    time.sleep(float(delays['layer']))
                except Exception as e:
                    error_msg = f"层前校准异常: {e}"
                    network_fault = True
                    break

                # ==== 全局 Z 轴贪吃蛇逻辑 (Y轴行进方向判断) ====
                is_layer_even = (z_idx % 2 == 0)
                y_list = list(range(sp['y_steps'])) if is_layer_even else list(range(sp['y_steps'] - 1, -1, -1))

                for y_idx in y_list:
                    if not self._is_running or network_fault: break
                    self._pause_event.wait() 

                    # ==== Y 轴换行步进 ====
                    try:
                        target_y = float(-y_idx * sp['step_mm'] * Y_AXIS_POLARITY)
                        hw.move_abs_mm('Y', target_y, speed, k)
                    except Exception as e:
                        error_msg = f"Y轴移动异常: {e}"
                        network_fault = True
                        break

                    # ==== X 轴极速飞点扫描 (全局贪吃蛇判断) ====
                    is_x_forward = (global_line_counter % 2 == 0)
                    
                    if is_x_forward:
                        real_start_x = 0.0 - overshoot_mm
                        real_end_x = line_length_mm + overshoot_mm
                    else:
                        real_start_x = line_length_mm + overshoot_mm
                        real_end_x = 0.0 - overshoot_mm

                    try:
                        # 1. 移动到带缓冲的起跑线
                        target_start_x = float(-real_start_x * X_AXIS_POLARITY)
                        hw.move_abs_mm('X', target_start_x, speed, k)
                        time.sleep(float(delays['line'])) 

                        # 2. 🔫 后台发令开枪：电机开始匀速冲刺
                        target_end_x = float(-real_end_x * X_AXIS_POLARITY)
                        motor_thread = threading.Thread(target=hw.move_abs_mm, args=('X', target_end_x, speed, k))
                        motor_thread.start()

                        # 3. ⏱ 掐表拦截：等待电机刚好压过真实的扫描起跑线
                        time.sleep(time_to_reach_zero)

                        # ==========================================
                        # ⚡ 4. 呼叫底层融合引擎！极速拿回精华数据
                        # ==========================================
                        # 返回的 result 是一个列表：[raw_means_list, proc_means_list]
                        result = hw.read_thz_line_fused(
                            total_samples_per_line, 
                            rate_hz, 
                            float(daq['volt_min']), 
                            float(daq['volt_max']), 
                            sp['x_steps']
                        )
                        
                        # 5. 等待电机刹车
                        motor_thread.join()

                        if len(result[0]) < sp['x_steps'] or result[0][0] == -999.0:
                            raise ValueError("底层 DAQ 或融合算法异常，拒绝处理无效数据")

                        raw_means_line = result[0]
                        proc_means_line = result[1]

                        # 🧠 空间映射：如果是反向扫，必须将数据翻转，保证图像绝对对齐
                        if not is_x_forward:
                            raw_means_line = raw_means_line[::-1]
                            proc_means_line = proc_means_line[::-1]

                        # 💥 极速填弹：把浓缩精华直接灌入数据库和 UI
                        for x_idx in range(sp['x_steps']):
                            if not self._is_running: break
                            
                            r_m = raw_means_line[x_idx]
                            p_m = proc_means_line[x_idx]
                            
                            # 存入 HDF5 库
                            # (抛弃了冗余的高频噪声数组，用 [p_m] 占位防错，极大缩小 H5 文件体积)
                            db.write_pixel(z_idx, x_idx, y_idx, [p_m], r_m, p_m)
                            
                            # 发射信号给 UI，界面会如丝般瞬间刷出一整行！
                            self.update_signal.emit(z_idx, y_idx, x_idx, [p_m], [p_m], r_m, p_m)

                    except Exception as e:
                        error_msg = f"飞点采集链断裂: {e}" 
                        network_fault = True
                        break 
                    
                    global_line_counter += 1

            # ===== 扫描结束复位 =====
            if not network_fault and self._is_running:
                try:
                    hw.move_abs_mm('X', 0.0, float(sp['speed_mm_s']), float(mot['pulse_ratio_k']))
                    hw.move_abs_mm('Y', 0.0, float(sp['speed_mm_s']), float(mot['pulse_ratio_k']))
                    hw.move_abs_mm('Z', 0.0, float(sp['speed_mm_s']), float(mot['pulse_ratio_k']))
                    self.status_signal.emit("✅ 3D 高速飞点扫描任务圆满结束，全轴安全回归。")
                except: pass
            elif not self._is_running and not network_fault:
                self.status_signal.emit("🛑 已人工制动，数据安全保存。")
            else:
                self.status_signal.emit(f"🛑 意外中止：{error_msg}")
                
        finally:
            try:
                db.close_and_export()
            except Exception as e:
                self.status_signal.emit(f"⚠️ 封盘清理失败: {e}")
            self.finished_signal.emit()

# ==========================================
# 🤖 重构版：Z 轴自动寻峰对焦雷达 (保持绝对值逻辑不变)
# ==========================================
class AutoFocusThread(QThread):
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(float, float) 

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._is_running = True
        self.processor = THzSignalProcessor()

    def stop(self): self._is_running = False

    def run(self):
        daq = self.cfg['hardware_daq']
        mot = self.cfg['hardware_motor']
        
        af_cfg = self.cfg.get('auto_focus', {})
        search_range_mm = float(af_cfg.get('search_range_mm', 10.0))
        step_mm = float(af_cfg.get('step_mm', 0.5))
        speed = float(af_cfg.get('speed_mm_s', 2.0))
        wait_time = float(af_cfg.get('wait_time_s', 0.2))

        try:
            hw = xmlrpc.client.ServerProxy("http://127.0.0.1:8000/")
            hw.reset_stop()
        except Exception as e:
            self.status_signal.emit(f"❌ 对焦通信异常: {e}")
            self.finished_signal.emit(0.0, 0.0)
            return

        best_z = 0.0
        max_abs_amp = -1.0 
        true_peak_volt = 0.0 
        
        start_z = -(search_range_mm / 2.0)
        steps = int(search_range_mm / step_mm)
        k = float(mot['pulse_ratio_k'])

        self.status_signal.emit(f"🔍 自动对焦启动 | 范围: {search_range_mm}mm | 步长: {step_mm}mm")
        
        try:
            hw.move_abs_mm('Z', start_z * Z_AXIS_POLARITY, speed, k)
            time.sleep(1.0) 
            
            for i in range(steps + 1):
                if not self._is_running: break
                
                current_z = start_z + i * step_mm
                hw.move_abs_mm('Z', current_z * Z_AXIS_POLARITY, speed, k)
                time.sleep(wait_time) 
                
                # 寻峰因为是单点测试，继续使用 read_raw 是安全的
                raw = hw.read_raw(int(daq['samples_per_pixel']), float(daq['sampling_rate_hz']), float(daq['volt_min']), float(daq['volt_max']))
                _, proc_mean, _ = self.processor.process_pixel(raw)
                
                current_abs_amp = abs(proc_mean)
                
                self.status_signal.emit(f"🔍 寻峰 Z={current_z:.2f}mm | 真实电压={proc_mean:.4f}V | 绝对光强={current_abs_amp:.4f}V")
                
                if current_abs_amp > max_abs_amp:
                    max_abs_amp = current_abs_amp
                    best_z = current_z
                    true_peak_volt = proc_mean 

            if self._is_running:
                self.status_signal.emit(f"🎯 寻峰完成！正在移至焦平面 Z={best_z:.2f}mm (峰值: {true_peak_volt:.4f}V)")
                hw.move_abs_mm('Z', best_z * Z_AXIS_POLARITY, speed, k)
                self.finished_signal.emit(best_z, true_peak_volt)
            else:
                self.finished_signal.emit(0.0, 0.0)
                
        except Exception as e:
            self.status_signal.emit(f"❌ 寻峰故障: {e}")
            self.finished_signal.emit(0.0, 0.0)
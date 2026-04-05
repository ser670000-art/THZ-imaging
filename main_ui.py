import sys
import xmlrpc.client
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QDoubleSpinBox, QSpinBox, 
                             QFormLayout, QGroupBox, QSlider, QLineEdit)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from scan_engine import ScanThread, MoveThread, AutoFocusThread, load_config, save_config

# ==========================================
# 🎨 全局顶级工业风样式表 (Siemens / NI 风格)
# ==========================================
GLOBAL_STYLE = """
QWidget {
    font-family: 'Microsoft YaHei', -apple-system, sans-serif;
    background-color: #EBF0F5; /* 科技浅灰蓝底色 */
    color: #2C3E50; /* 沉稳深炭灰 */
}

/* 悬浮卡片式 GroupBox */
QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #D1D9E6;
    border-radius: 8px;
    margin-top: 24px;
    padding-top: 15px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 20px;
    top: -10px;
    background-color: #003366; /* 核心深蓝 */
    color: #FFFFFF;
    padding: 6px 16px;
    border-radius: 4px;
    font-size: 15px;
    font-weight: bold;
}

/* 统一输入框风格 */
QDoubleSpinBox, QSpinBox, QLineEdit {
    background-color: #F8FAFC;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 6px;
    font-size: 14px;
    color: #1E293B;
    min-width: 80px;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {
    border: 2px solid #00529B;
    background-color: #FFFFFF;
}

/* 基础按钮风格 */
QPushButton {
    background-color: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 4px;
    padding: 8px 12px;
    color: #334155;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover { background-color: #E2E8F0; }
QPushButton:pressed { background-color: #CBD5E1; }
QPushButton:disabled { background-color: #E2E8F0; color: #94A3B8; border: none; }

/* 核心行动按钮 (Call to Action) */
QPushButton#btnActionBlue {
    background-color: #00529B; color: white; border: none;
}
QPushButton#btnActionBlue:hover { background-color: #003F7A; }

QPushButton#btnGiantStart {
    background-color: #107C10; color: white; border: none;
    font-size: 20px; padding: 18px; border-radius: 6px;
}
QPushButton#btnGiantStart:hover { background-color: #0B5A0B; }

QPushButton#btnEmergency {
    background-color: #D13438; color: white; border: none;
    font-size: 18px; padding: 12px; border-radius: 6px;
}
QPushButton#btnEmergency:hover { background-color: #A4262C; }

/* 状态栏大屏显示 */
QLabel#statusScreen {
    background-color: #1E293B;
    color: #4ADE80; /* 荧光绿终端字 */
    font-family: 'Consolas', monospace;
    font-size: 15px;
    padding: 12px;
    border-radius: 6px;
    border: 2px inset #0F172A;
}
"""

# ==========================================
# 🖥️ 独立窗口 A：波形双通道对比舱
# ==========================================
class WaveformWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("THz 时域波形监测矩阵 (Time-Domain Waveform Matrix)")
        self.resize(1100, 750)
        self.setStyleSheet(GLOBAL_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        display_layout = QHBoxLayout()
        display_layout.setSpacing(20)
        
        # 处理前数据组
        raw_group = QGroupBox("通道 1：原始太赫兹信号 (Raw Signal)")
        raw_layout = QVBoxLayout(raw_group)
        self.label_raw = QLabel("-0.0000 V")
        self.label_raw.setFont(QFont("Consolas", 42, QFont.Bold))
        self.label_raw.setStyleSheet("color: #64748B; background: transparent; border: none;")
        self.label_raw.setAlignment(Qt.AlignCenter)
        raw_layout.addWidget(self.label_raw)
        
        # 处理后数据组
        proc_group = QGroupBox("通道 2：数字滤波后信号 (Processed Signal)")
        proc_group.setStyleSheet(proc_group.styleSheet() + " QGroupBox::title { background-color: #D83B01; }") # 桔色高亮
        proc_layout = QVBoxLayout(proc_group)
        self.label_proc = QLabel("-0.0000 V")
        self.label_proc.setFont(QFont("Consolas", 56, QFont.Bold))
        self.label_proc.setStyleSheet("color: #D83B01; background: transparent; border: none;") 
        self.label_proc.setAlignment(Qt.AlignCenter)
        proc_layout.addWidget(self.label_proc)
        
        display_layout.addWidget(raw_group)
        display_layout.addWidget(proc_group)
        layout.addLayout(display_layout, stretch=1)

        # 图表背景改白，线条加粗加深
        pg.setConfigOption('background', '#FFFFFF')
        pg.setConfigOption('foreground', '#333333')
        
        charts_layout = QVBoxLayout()
        self.plot_raw = pg.PlotWidget(title="Channel 1: Raw DAQ Input")
        self.plot_raw.showGrid(x=True, y=True, alpha=0.5)
        self.curve_raw = self.plot_raw.plot(pen=pg.mkPen(color='#94A3B8', width=2.5)) 
        charts_layout.addWidget(self.plot_raw)

        self.plot_proc = pg.PlotWidget(title="Channel 2: DSP Output")
        self.plot_proc.showGrid(x=True, y=True, alpha=0.5)
        self.curve_proc = self.plot_proc.plot(pen=pg.mkPen(color='#D83B01', width=3.5)) 
        charts_layout.addWidget(self.plot_proc)

        layout.addLayout(charts_layout, stretch=5)

    def apply_config(self, cfg):
        samples = cfg['hardware_daq']['samples_per_pixel']
        self.plot_raw.setYRange(-0.1, 0.01, padding=0)
        self.plot_raw.setXRange(0, samples, padding=0)
        self.plot_proc.setYRange(-0.1, 0.01, padding=0)
        self.plot_proc.setXRange(0, samples, padding=0)

    def update_view(self, raw_data, proc_data, raw_mean, proc_mean):
        self.curve_raw.setData(raw_data)
        self.curve_proc.setData(proc_data)
        self.label_raw.setText(f"{raw_mean:.4f} V")
        self.label_proc.setText(f"{proc_mean:.4f} V")

# ==========================================
# 🖥️ 独立窗口 B：3D 层析指挥总控舱
# ==========================================
class ImagingWindow(QWidget):
    def __init__(self, waveform_window):
        super().__init__()
        self.waveform_window = waveform_window
        self.cfg = load_config() 
        self.waveform_window.apply_config(self.cfg) 

        self.setWindowTitle("太赫兹三维层析高分辨成像系统 (High-Resolution THz 3D Tomography)")
        self.resize(1400, 950) # 窗口再拉大，显得更从容
        self.setStyleSheet(GLOBAL_STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(25)

        # 左侧：图像显示区
        img_panel = QVBoxLayout()
        self.img_view = pg.ImageView()
        self.img_view.ui.histogram.hide(); self.img_view.ui.roiBtn.hide(); self.img_view.ui.menuBtn.hide()
        self.img_view.setPredefinedGradient('plasma') 
        
        self.roi = pg.RectROI([2, 2], [5, 5], pen=pg.mkPen(color='#00FF00', width=4))
        self.img_view.addItem(self.roi)
        self.roi.hide()
        self.is_preview_mode = False

        img_panel.addWidget(self.img_view, stretch=10)

        slider_layout = QHBoxLayout()
        self.label_z_info = QLabel("当前观测层级: Z = 1 / 1")
        self.label_z_info.setStyleSheet("font-weight: bold; font-size: 18px; color: #003366;")
        self.z_slider = QSlider(Qt.Horizontal)
        self.z_slider.setMinimum(0)
        self.z_slider.setMaximum(0)
        self.z_slider.setStyleSheet("QSlider::handle:horizontal { background: #00529B; width: 24px; margin: -8px 0; border-radius: 12px; } QSlider::groove:horizontal { height: 8px; background: #CBD5E1; border-radius: 4px; }")
        self.z_slider.valueChanged.connect(self.on_slider_changed)
        
        slider_layout.addWidget(self.label_z_info)
        slider_layout.addSpacing(20)
        slider_layout.addWidget(self.z_slider, stretch=1)
        img_panel.addLayout(slider_layout)
        layout.addLayout(img_panel, stretch=7) # 图像区域占比增大

        # 右侧：主控台
        control_panel = QVBoxLayout()
        
        # 模块 1：智能辅助组
        auto_group = QGroupBox("智能探测辅助系统 (AI Assist)")
        auto_layout = QVBoxLayout(auto_group)
        auto_layout.setSpacing(12)
        
        self.btn_auto_focus = QPushButton("🔍 Z轴自动寻峰对焦")
        self.btn_auto_focus.setObjectName("btnActionBlue")
        self.btn_auto_focus.clicked.connect(self.start_auto_focus)
        
        self.btn_preview = QPushButton("🚀 极速低清全景预览")
        self.btn_preview.setObjectName("btnActionBlue")
        self.btn_preview.clicked.connect(self.start_preview_scan)
        
        self.btn_apply_roi = QPushButton("🎯 锁定红框进入高精扫描")
        self.btn_apply_roi.setStyleSheet("QPushButton { background-color: #D83B01; color: white; border: none; } QPushButton:disabled { background-color: #E2E8F0; color: #94A3B8; }")
        self.btn_apply_roi.clicked.connect(self.apply_roi)
        self.btn_apply_roi.setEnabled(False)
        
        auto_layout.addWidget(self.btn_auto_focus)
        auto_layout.addWidget(self.btn_preview)
        auto_layout.addWidget(self.btn_apply_roi)
        control_panel.addWidget(auto_group)

        # 模块 2：手动与参数
        manual_group = QGroupBox("空间坐标与硬件定位 (Positioning)")
        manual_layout = QFormLayout(manual_group)
        manual_layout.setVerticalSpacing(12)
        
        self.target_x, self.target_y, self.target_z = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for box in [self.target_x, self.target_y, self.target_z]:
            box.setRange(-500.0, 500.0); box.setDecimals(2)
        
        lbl_style = "font-size: 14px; font-weight: bold; color: #475569;"
        lbl_x = QLabel("目标 X (mm):"); lbl_x.setStyleSheet(lbl_style)
        lbl_y = QLabel("目标 Y (mm):"); lbl_y.setStyleSheet(lbl_style)
        lbl_z = QLabel("目标 Z (mm):"); lbl_z.setStyleSheet(lbl_style)

        manual_layout.addRow(lbl_x, self.target_x)
        manual_layout.addRow(lbl_y, self.target_y)
        manual_layout.addRow(lbl_z, self.target_z)
        
        btn_layout_manual = QHBoxLayout()
        self.btn_move = QPushButton("执行坐标位移")
        self.btn_move.clicked.connect(self.move_to_target)
        self.btn_set_zero = QPushButton("当前点设为绝对原点")
        self.btn_set_zero.clicked.connect(self.set_zero_point)
        btn_layout_manual.addWidget(self.btn_move); btn_layout_manual.addWidget(self.btn_set_zero)
        manual_layout.addRow(btn_layout_manual)
        control_panel.addWidget(manual_group)
        
        config_group = QGroupBox("三维扫描参数系 (Scan Parameters)")
        config_layout = QFormLayout(config_group)
        config_layout.setVerticalSpacing(10)
        self.x_box, self.y_box, self.z_box = QSpinBox(), QSpinBox(), QSpinBox()
        for box in [self.x_box, self.y_box, self.z_box]: box.setRange(1, 1000)
        self.step_box, self.z_step_box, self.speed_box = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for box in [self.step_box, self.z_step_box, self.speed_box]: box.setSingleStep(0.1)
            
        config_layout.addRow(QLabel("X轴扫描点数:", styleSheet=lbl_style), self.x_box)
        config_layout.addRow(QLabel("Y轴扫描点数:", styleSheet=lbl_style), self.y_box)
        config_layout.addRow(QLabel("平面分辨率 (mm):", styleSheet=lbl_style), self.step_box)
        config_layout.addRow(QLabel("Z轴深度层数:", styleSheet=lbl_style), self.z_box)
        config_layout.addRow(QLabel("深度分辨率 (mm):", styleSheet=lbl_style), self.z_step_box)
        config_layout.addRow(QLabel("探头移动速度 (mm/s):", styleSheet=lbl_style), self.speed_box)
        control_panel.addWidget(config_group)
        self.sync_ui_from_json()

        # 状态栏 (仪表盘黑底绿字风格)
        self.label_status = QLabel("> SYSTEM STANDBY. Ready for instructions.")
        self.label_status.setObjectName("statusScreen")
        self.label_status.setWordWrap(True)
        control_panel.addWidget(self.label_status)
        control_panel.addStretch()

        # 核心按钮区 (极其巨大)
        self.btn_start = QPushButton("▶ 启动高精三维层析 (START SCAN)")
        self.btn_start.setObjectName("btnGiantStart")
        self.btn_start.clicked.connect(self.start_start)
        control_panel.addWidget(self.btn_start)

        pause_layout = QHBoxLayout()
        self.btn_pause = QPushButton("⏸ 挂起任务 (PAUSE)")
        self.btn_pause.setStyleSheet("QPushButton { background-color: #F59E0B; color: white; padding: 12px; font-size: 15px; border: none; border-radius: 4px; }")
        self.btn_pause.clicked.connect(self.pause_scan); self.btn_pause.setEnabled(False)
        
        self.btn_resume = QPushButton("▶️ 恢复任务 (RESUME)")
        self.btn_resume.setStyleSheet("QPushButton { background-color: #00529B; color: white; padding: 12px; font-size: 15px; border: none; border-radius: 4px; }")
        self.btn_resume.clicked.connect(self.resume_scan); self.btn_resume.setEnabled(False)
        pause_layout.addWidget(self.btn_pause); pause_layout.addWidget(self.btn_resume)
        control_panel.addLayout(pause_layout)

        self.btn_stop = QPushButton("🛑 紧急制动 (EMERGENCY STOP)")
        self.btn_stop.setObjectName("btnEmergency")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_scan)
        control_panel.addWidget(self.btn_stop)

        layout.addLayout(control_panel, stretch=3)
        
        self.scan_thread = None; self.move_thread = None; self.af_thread = None
        self.img_data_3d = np.zeros((1, 10, 10))
        self.last_h5_file = None 

    # 🤖 [逻辑代码完全保持不变，确保直接对接你的系统]
    def start_auto_focus(self):
        self.update_status("> INITIATING AUTO-FOCUS SEQUENCE...")
        self.btn_auto_focus.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.af_thread = AutoFocusThread(self.cfg) 
        self.af_thread.status_signal.connect(self.update_status)
        self.af_thread.finished_signal.connect(self.auto_focus_finished)
        self.af_thread.start()

    def auto_focus_finished(self, best_z, max_amp):
        self.btn_auto_focus.setEnabled(True)
        self.btn_start.setEnabled(True)
        if best_z != 0.0 or max_amp != -9999.0:
            self.target_z.setValue(best_z)
            self.update_status(f"> SUCCESS: Optimal focal point found at Z={best_z:.2f}mm. Target updated.")

    def start_preview_scan(self):
        self.sync_json_from_ui()
        self.high_res_cfg = load_config() 
        preview_step = 2.0 
        self.cfg['scan_params']['step_mm'] = preview_step
        self.cfg['scan_params']['x_steps'] = 20
        self.cfg['scan_params']['y_steps'] = 20
        self.cfg['scan_params']['z_steps'] = 1
        
        self.is_preview_mode = True
        self.roi.hide()
        self.btn_apply_roi.setEnabled(False)
        self.update_status("> LAUNCHING RAPID 2D PREVIEW SCAN...")
        self.start_scan() 

    def apply_roi(self):
        pos = self.roi.pos()
        size = self.roi.size()
        preview_step = 2.0
        offset_y_mm = pos[0] * preview_step
        offset_x_mm = pos[1] * preview_step
        width_mm = size[0] * preview_step
        height_mm = size[1] * preview_step
        
        high_res_step = self.step_box.value()
        new_y_steps = max(1, int(width_mm / high_res_step))
        new_x_steps = max(1, int(height_mm / high_res_step))
        
        self.target_y.setValue(-offset_y_mm)
        self.target_x.setValue(-offset_x_mm)
        
        self.x_box.setValue(new_x_steps)
        self.y_box.setValue(new_y_steps)
        
        self.roi.hide()
        self.btn_apply_roi.setEnabled(False)
        self.update_status(f"> ROI LOCKED. New Grid: {new_x_steps}x{new_y_steps}. Ready for high-res displacement.")

    def set_last_file(self, file_path): self.last_h5_file = file_path

    def set_zero_point(self):
        try:
            hw = xmlrpc.client.ServerProxy("http://127.0.0.1:8000/")
            hw.set_absolute_zero()
            self.target_x.setValue(0.0); self.target_y.setValue(0.0); self.target_z.setValue(0.0)
            self.update_status("> CALIBRATION SUCCESS: Absolute zero point confirmed.")
        except Exception as e:
            self.update_status(f"> ERROR: Hardware communication failure - {e}")

    def move_to_target(self):
        self.btn_move.setEnabled(False); self.btn_start.setEnabled(False); self.btn_set_zero.setEnabled(False); self.btn_stop.setEnabled(True) 
        self.move_thread = MoveThread(self.target_x.value(), self.target_y.value(), self.target_z.value(), self.speed_box.value(), self.cfg['hardware_motor']['pulse_ratio_k'])
        self.move_thread.status_signal.connect(self.update_status)
        self.move_thread.finished_signal.connect(self.move_finished)
        self.move_thread.start()
        
    def move_finished(self):
        self.btn_move.setEnabled(True); self.btn_start.setEnabled(True); self.btn_set_zero.setEnabled(True); self.btn_stop.setEnabled(False)

    def sync_ui_from_json(self):
        sp = self.cfg['scan_params']
        self.x_box.setValue(sp['x_steps']); self.y_box.setValue(sp['y_steps']); self.z_box.setValue(sp['z_steps'])
        self.step_box.setValue(sp['step_mm']); self.z_step_box.setValue(sp.get('z_step_mm', 0.2)); self.speed_box.setValue(sp['speed_mm_s'])

    def sync_json_from_ui(self):
        self.cfg = load_config()
        sp = self.cfg['scan_params']
        sp['x_steps'], sp['y_steps'], sp['z_steps'] = self.x_box.value(), self.y_box.value(), self.z_box.value()
        sp['step_mm'], sp['z_step_mm'], sp['speed_mm_s'] = self.step_box.value(), self.z_step_box.value(), self.speed_box.value()
        save_config(self.cfg)
        self.waveform_window.apply_config(self.cfg)

    def pause_scan(self):
        if self.scan_thread:
            self.scan_thread.pause_scan()
            self.btn_pause.setEnabled(False); self.btn_resume.setEnabled(True)
            self.update_status("> WARNING: Scanning protocol suspended.")

    def resume_scan(self):
        if self.scan_thread:
            self.scan_thread.resume_scan()
            self.btn_pause.setEnabled(True); self.btn_resume.setEnabled(False)
            self.update_status("> SCAN RESUMED.")

    def start_start(self):
        if not self.is_preview_mode: self.sync_json_from_ui() 
        self.btn_start.setEnabled(False); self.btn_move.setEnabled(False); self.btn_set_zero.setEnabled(False); self.btn_stop.setEnabled(True); self.btn_pause.setEnabled(True); self.btn_resume.setEnabled(False)
        sp = self.cfg['scan_params']
        self.img_data_3d = np.zeros((sp['z_steps'], sp['y_steps'], sp['x_steps']))
        self.z_slider.setMaximum(sp['z_steps'] - 1)
        self.z_slider.setValue(0)
        self.on_slider_changed()

        self.scan_thread = ScanThread(self.cfg)
        self.scan_thread.file_created_signal.connect(self.set_last_file)
        self.scan_thread.update_signal.connect(self.update_image)
        self.scan_thread.update_signal.connect(lambda z, y, x, raw, proc, r_m, p_m: self.waveform_window.update_view(raw, proc, r_m, p_m))
        self.scan_thread.status_signal.connect(self.update_status)
        self.scan_thread.finished_signal.connect(self.scan_finished)
        self.scan_thread.start()

    def stop_scan(self):
        self.btn_stop.setEnabled(False)
        self.update_status("> CRITICAL: Emergency stop engaged. Saving memory buffers...")
        if self.scan_thread: self.scan_thread.stop()
        if hasattr(self, 'move_thread') and self.move_thread: self.move_thread.stop()
        try: xmlrpc.client.ServerProxy("http://127.0.0.1:8000/").emergency_stop() 
        except Exception: pass

    def update_image(self, z_idx, y_idx, x_idx, raw_data, raw_mean, proc_mean):
        self.img_data_3d[z_idx, y_idx, x_idx] = proc_mean
        if self.z_slider.value() == z_idx:
            self.img_view.setImage(self.img_data_3d[z_idx, :, :], autoRange=False)

    def on_slider_changed(self):
        current_z = self.z_slider.value()
        self.label_z_info.setText(f"当前观测层级: Z = {current_z + 1} / {self.cfg['scan_params']['z_steps']}")
        self.img_view.setImage(self.img_data_3d[current_z, :, :], autoRange=False)

    def update_status(self, text):
        if "🛑" in text or "❌" in text or "ERROR" in text or "CRITICAL" in text: 
            self.label_status.setStyleSheet("QLabel#statusScreen { background-color: #450a0a; color: #f87171; border: 2px inset #220505; }")
        elif "⚠️" in text or "⏸" in text or "WARNING" in text: 
            self.label_status.setStyleSheet("QLabel#statusScreen { background-color: #422006; color: #facc15; border: 2px inset #211003; }")
        else: 
            self.label_status.setStyleSheet("QLabel#statusScreen { background-color: #1E293B; color: #4ADE80; border: 2px inset #0F172A; }")
        self.label_status.setText(text)

    def scan_finished(self):
        self.btn_start.setEnabled(True); self.btn_move.setEnabled(True); self.btn_set_zero.setEnabled(True); self.btn_stop.setEnabled(False); self.btn_pause.setEnabled(False); self.btn_resume.setEnabled(False)
        
        if getattr(self, 'is_preview_mode', False):
            self.roi.show() 
            self.btn_apply_roi.setEnabled(True)
            self.update_status("> PREVIEW COMPLETE. Awaiting ROI selection input...")
            
            self.is_preview_mode = False
            self.cfg = self.high_res_cfg 
            self.sync_ui_from_json() 

if __name__ == '__main__':
    app = QApplication(sys.argv)
    wave_win = WaveformWindow()
    img_win = ImagingWindow(waveform_window=wave_win)
    wave_win.show()
    img_win.show()
    sys.exit(app.exec_())
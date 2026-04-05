import h5py
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import tkinter as tk
from tkinter import filedialog
import json

# ==========================================
# ⚙️ 1. 用户配置区 (在此修改观察坐标)
# ==========================================
USER_X = 11  # 您想观察的 X 坐标位置
USER_Y = 9  # 您想观察的 Y 坐标位置

# 从 json 读取配置 (假设文件名为 config.json)
config_path = 'config.json'
top_n = 10 # 默认值
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            top_n = config.get("top_n", 30)
    except Exception as e:
        print(f"⚠️ 读取配置文件失败: {e}")

print("======================================================")
print(" 🚀 太赫兹光束质量 (Beam Quality) 独立分析工具")
print("======================================================")

# ==========================================
# 📂 2. 选择文件并读取数据
# ==========================================
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)

h5_filename = filedialog.askopenfilename(
    title="选择 .h5 数据文件",
    filetypes=[("HDF5 数据", "*.h5")]
)

if not h5_filename:
    sys.exit()

try:
    with h5py.File(h5_filename, 'r') as f:
        data = f['image_mean_processed'][:]
except Exception as e:
    print(f"读取失败: {e}")
    sys.exit()

# ==========================================
# 🧠 3. 核心数学计算与终端 Top N 报告
# ==========================================
intensity = np.abs(data)
Z_len, Y_len, X_len = intensity.shape

# 确保用户输入的坐标不越界
USER_X = min(max(0, USER_X), X_len - 1)
USER_Y = min(max(0, USER_Y), Y_len - 1)

# --- 终端报告：寻找全空间前 N 个极大值点 ---
print(f"\n🏆 全空间光强排名前 {top_n} 的坐标点报告：")
print("-" * 60)
print(f"{'排名':<6} | {'光强 (V)':<12} | {'X':<6} | {'Y':<6} | {'Z (层)':<6}")
print("-" * 60)

flat_indices = np.argsort(intensity.ravel())[-top_n:][::-1]
for i, idx in enumerate(flat_indices):
    z_idx, y_idx, x_idx = np.unravel_index(idx, intensity.shape)
    val = intensity[z_idx, y_idx, x_idx]
    print(f"#{i+1:<5} | {val:<12.6f} | {x_idx:<6} | {y_idx:<6} | {z_idx:<6}")
print("-" * 60)
print(f"📍 当前固定观察坐标: X={USER_X}, Y={USER_Y}\n")

# --- 计算曲线数据 ---
z_axis = np.arange(Z_len)
peak_intensities = [] # 每一层最亮的点
fixed_point_intensities = intensity[:, USER_Y, USER_X] # 您指定的固定点

fwhm_x = []
fwhm_y = []

for i in range(Z_len):
    z_slice = intensity[i]
    p_max = np.max(z_slice)
    peak_intensities.append(p_max)
    
    y_p, x_p = np.unravel_index(np.argmax(z_slice), z_slice.shape)
    half_max = p_max / 2.0
    
    line_x = z_slice[y_p, :]
    above_hm_x = np.where(line_x >= half_max)[0]
    fwhm_x.append(len(above_hm_x) if len(above_hm_x) > 0 else 0)
    
    line_y = z_slice[:, x_p]
    above_hm_y = np.where(line_y >= half_max)[0]
    fwhm_y.append(len(above_hm_y) if len(above_hm_y) > 0 else 0)

focal_z = np.argmax(peak_intensities)

# ==========================================
# 🖥️ 4. 构建分析看板
# ==========================================
fig = make_subplots(
    rows=3, cols=1,
    row_heights=[0.4, 0.3, 0.3],
    vertical_spacing=0.1,
    subplot_titles=(
        "2D 实时光斑截面", 
        f"光强能量演化 (对比：层最大值 vs 固定点 X:{USER_X}, Y:{USER_Y})", 
        "光斑尺寸演化 (FWHM vs Z)"
    )
)

# --- 第一行：2D 热力图 ---
fig.add_trace(
    go.Heatmap(
        z=intensity[focal_z],
        colorscale=[[0, '#000022'], [0.15, '#0d4bbf'], [0.35, '#00ccff'],
                    [0.55, '#00ff00'], [0.75, '#ffff00'], [0.9, '#ff0000'], [1, '#ffffff']],
        zmin=0, zmax=0.22,
        name="截面图"
    ), row=1, col=1
)

# --- 第二行：光强能量演化图 (核心修改区) ---
# 原有的动态峰值曲线
fig.add_trace(
    go.Scatter(x=z_axis, y=peak_intensities, name="各层最强点(动态)", 
               line=dict(color='cyan', width=2, dash='dot')),
    row=2, col=1
)
# 🎯 新增的固定位置曲线
fig.add_trace(
    go.Scatter(x=z_axis, y=fixed_point_intensities, name=f"固定点({USER_X},{USER_Y})", 
               line=dict(color='yellow', width=3)),
    row=2, col=1
)

# --- 第三行：FWHM 演化 ---
fig.add_trace(
    go.Scatter(x=z_axis, y=fwhm_x, name="X-FWHM", line=dict(color='#ff7f0e')),
    row=3, col=1
)
fig.add_trace(
    go.Scatter(x=z_axis, y=fwhm_y, name="Y-FWHM", line=dict(color='#2ca02c')),
    row=3, col=1
)

# ==========================================
# 🎛️ 5. 联动滑块与美化
# ==========================================
steps = []
for i in range(Z_len):
    step = dict(
        method="update",
        args=[
            {"z": [intensity[i]]},
            {"shapes": [
                dict(type="line", x0=i, x1=i, y0=0, y1=1, yref="y2", line=dict(color="red", dash="dash"), xref="x2"),
                dict(type="line", x0=i, x1=i, y0=0, y1=1, yref="y3", line=dict(color="red", dash="dash"), xref="x3")
            ]}
        ],
        label=f"层 {i}"
    )
    steps.append(step)

sliders = [dict(
    active=int(focal_z),
    currentvalue={"prefix": "🔍 正在分析 Z 轴深度层: "},
    pad={"t": 50}, steps=steps
)]

fig.update_layout(
    template="plotly_dark", height=900, sliders=sliders,
    yaxis1=dict(autorange="reversed", scaleanchor="x1"),
    yaxis2=dict(range=[0, 0.25], title="光强 (V)"),
    yaxis3=dict(title="FWHM (Pixels)"),
    paper_bgcolor='#0a0a0a', plot_bgcolor='#0a0a0a'
)

# 初始指示红线
fig.add_shape(type="line", x0=focal_z, x1=focal_z, y0=0, y1=1, yref="y2", line=dict(color="red", dash="dash"), row=2, col=1)
fig.add_shape(type="line", x0=focal_z, x1=focal_z, y0=0, y1=1, yref="y3", line=dict(color="red", dash="dash"), row=3, col=1)

# ==========================================
# 💾 6. 保存
# ==========================================
save_name = f'Beam_Quality_Report_{os.path.basename(h5_filename)}.html'
fig.write_html(save_name, auto_open=True)
print(f"📊 分析报告已生成: {save_name}")
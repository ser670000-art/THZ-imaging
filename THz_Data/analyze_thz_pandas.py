import h5py
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import tkinter as tk
from tkinter import filedialog

print("======================================================")
print(" 🧊 太赫兹 3D 层析分析仪 - 双屏联动检测版 (0.22V 阈值版)")
print("======================================================")

# ==========================================
# 📂 1. 文件选取
# ==========================================
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)

h5_filename = filedialog.askopenfilename(
    title="选取太赫兹 3D 数据 (.h5)",
    initialdir=os.getcwd(),
    filetypes=[("HDF5 数据文件", "*.h5"), ("所有文件", "*.*")]
)

if not h5_filename:
    print("❌ 未选择文件，退出。")
    sys.exit()

try:
    with h5py.File(h5_filename, 'r') as f:
        data = f['image_mean_processed'][:]
except Exception as e:
    print(f"❌ 读取失败: {e}")
    sys.exit()

# ==========================================
# 🧠 2. 数据预处理
# ==========================================
intensity = np.abs(data)

# 🎯 关键修正：不再使用 percentile 自动削峰，
# 否则数据最高点会被焊死在 0.19，导致无法触发 0.22 的白色。
# 我们直接保留原始数据。

Z_len, Y_len, X_len = intensity.shape

# 展平 3D 点云
grid_z, grid_y, grid_x = np.indices(intensity.shape)
X_flat = grid_x.flatten()
Y_flat = grid_y.flatten()
Z_flat = grid_z.flatten()
values_flat = intensity.flatten()

# ==========================================
# 🎨 3. 顶配彩虹色带
# ==========================================
# 🎯 强制设定量程上限为 0.22，所有大于等于 0.22 的点会自动对应到白色 (#ffffff)
cmin, cmax = 0.05, 0.22

custom_colorscale = [
    [0.0,  '#000022'], [0.15, '#0d4bbf'], [0.35, '#00ccff'],
    [0.55, '#00ff00'], [0.75, '#ffff00'], [0.90, '#ff0000'], [1.0,  '#ffffff']
]

# ==========================================
# 🖥️ 4. 构建双屏布局
# ==========================================
fig = make_subplots(
    rows=1, cols=2,
    column_widths=[0.6, 0.4],
    specs=[[{'type': 'scene'}, {'type': 'xy'}]],
    subplot_titles=(f"3D 立体层析 (Z 轴总深度: {Z_len})", "2D X-Y 截面光强分布")
)

# --- Trace 0: 3D Volume ---
fig.add_trace(
    go.Volume(
        x=X_flat, y=Y_flat, z=Z_flat,
        value=values_flat,
        isomin=cmin, isomax=cmax,
        opacity=0.3, surface_count=20,
        colorscale=custom_colorscale,
        slices_z=dict(show=True, locations=[0]),
        showscale=True,
        colorbar=dict(
            title=dict(text="光强", font=dict(color="white")),
            x=-0.1,
            tickfont=dict(color="white"),
            tickcolor="white"
        ),
        hovertemplate="x: %{x}<br>y: %{y}<br>z(深度): %{z}<br>光强: %{value:.6f}<extra></extra>"
    ),
    row=1, col=1
)

# --- Trace 1: 2D Heatmap ---
fig.add_trace(
    go.Heatmap(
        z=intensity[0],
        colorscale=custom_colorscale,
        zmin=cmin, zmax=cmax,
        showscale=False,
        hovertemplate="x: %{x}<br>y: %{y}<br>光强: %{z:.6f}<extra></extra>"
    ),
    row=1, col=2
)

# ==========================================
# 🎛️ 5. 构建联动滑块与交互按钮
# ==========================================
steps = []
for i in range(Z_len):
    step = dict(
        method="restyle",
        args=[
            {
                "slices_z.locations": [[i]],
                "z": [None, intensity[i]]
            },
            [0, 1]
        ],
        label=f"层 {i}"
    )
    steps.append(step)

sliders = [dict(
    active=0,
    currentvalue={"prefix": "🔍 正在查看 Z 轴深度层: ", "font": {"color": "#00ff00", "size": 16}},
    pad={"t": 50},
    steps=steps,
    font=dict(color="white")
)]

updatemenus = [
    dict(
        type="buttons", 
        direction="right", 
        x=0.05, 
        y=1.1,
        font=dict(color="white"),
        buttons=[
            dict(label="🔄 3D视角", method="relayout", args=[{"scene.camera": dict(eye=dict(x=1.5, y=1.5, z=1.2))}]),
            dict(label="⬇️ 俯视(XY)", method="relayout", args=[{"scene.camera": dict(eye=dict(x=0, y=0, z=2.5), up=dict(x=0, y=1, z=0))}]),
            dict(label="➡️ 正视(XZ)", method="relayout", args=[{"scene.camera": dict(eye=dict(x=0, y=-2.5, z=0))}]),
            dict(label="↗️ 侧视(YZ)", method="relayout", args=[{"scene.camera": dict(eye=dict(x=2.5, y=0, z=0))}]),
        ]
    )
]

# ==========================================
# 🎨 6. 最终美化布局
# ==========================================
file_basename = os.path.basename(h5_filename)

fig.update_layout(
    title=dict(text=f"太赫兹 3D 智能分析系统 - {file_basename}", font=dict(color='white', size=20)),
    paper_bgcolor='#0a0a0a', plot_bgcolor='#0a0a0a',
    sliders=sliders,
    updatemenus=updatemenus,
    scene=dict(
        xaxis=dict(title='X轴', gridcolor='#333', color='white'),
        yaxis=dict(title='Y轴', gridcolor='#333', color='white'),
        zaxis=dict(title='Z轴(深度)', gridcolor='#333', color='white'),
        aspectmode='data'
    ),
    yaxis=dict(
        title='Y 方向 (列)',
        autorange='reversed',
        color='white', gridcolor='#333'
    ),
    xaxis2=dict(title='X 方向 (行)', color='white', gridcolor='#333'),
    margin=dict(l=50, r=50, b=100, t=100)
)

# ==========================================
# 💾 7. 保存并启动
# ==========================================
save_name = f'THz_DualView_Strict_022_{os.path.splitext(file_basename)[0]}.html'
print(f"✅ 处理完成！当前量程锁定为 0.05 - 0.22V。")
fig.write_html(save_name, auto_open=True)
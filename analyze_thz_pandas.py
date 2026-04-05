import h5py
import numpy as np
import plotly.graph_objects as go
import sys

print("======================================================")
print(" 🎓 太赫兹 3D 立体成像 - SCI 学术论文风优化版")
print("======================================================")

# ==========================================
# 📂 1. 读取 HDF5 3D 数据
# ==========================================
h5_filename = '090601_THz_3D_Sample_15x20x75_P20.h5'

try:
    with h5py.File(h5_filename, 'r') as f:
        data = f['image_mean_processed'][:]
except FileNotFoundError:
    print(f"❌ 找不到文件 {h5_filename}")
    sys.exit()

# ==========================================
# 🧠 2. 数据预处理与坐标系物理映射
# ==========================================
# 提取太赫兹光强（绝对值振幅）
intensity = np.abs(data)

# 构建物理网格索引 (Z, Y, X)
grid_z, grid_y, grid_x = np.indices(intensity.shape)

# 保留之前的正确映射：迎面看向 XY 切面
X_plotly = grid_y.flatten()  # 物理 Y 轴 (横向)
Y_plotly = grid_z.flatten()  # 物理 Z 轴 (深度)
Z_plotly = grid_x.flatten()  # 物理 X 轴 (纵向)
values = intensity.flatten()

# ==========================================
# 🎨 3. 构建 3D 体绘制图 (学术风核心调优)
# ==========================================
print("🎨 正在渲染高精度学术 3D 模型...")

v_max = values.max()

fig = go.Figure(data=go.Volume(
    x=X_plotly,  
    y=Y_plotly,  
    z=Z_plotly,  
    value=values,
    # 阈值稍微拉高一点，确保周围背景干净无杂波，突出主体
    isomin=v_max * 0.1,           
    isomax=v_max,                 
    opacity=0.35,                 # 稍微提高透明度，让内部特征更加凝实
    surface_count=25,             # 增加等值面数量，让渐变更平滑细腻
    
    # 🎓 【学术专属色带】Viridis：自然杂志(Nature)等顶刊推荐的标准科学色带
    colorscale='Viridis',         
    
    # 🎓 【图例美化】给 Colorbar 增加黑色边框，修改字体
    colorbar=dict(
        title=dict(text='THz Intensity (arb. u.)', font=dict(family="Arial", size=14, color="black")),
        tickfont=dict(family="Arial", size=12, color="black"),
        thickness=20,
        len=0.7,
        outlinewidth=1,           # 外边框线宽
        outlinecolor='black'      # 外边框颜色
    ),
    
    # 💡 【光照材质】加入真实物理光照，增加 3D 渲染的高级质感
    lighting=dict(
        ambient=0.6,    # 环境光
        diffuse=0.8,    # 漫反射
        specular=0.5,   # 高光
        roughness=0.5   # 粗糙度
    )
))

# ==========================================
# 🖥️ 4. 学术画布与坐标轴规范化
# ==========================================
fig.update_layout(
    # 学术论文通常把标题写在 Caption 里，所以主图标题可留空或尽量简洁
    title=dict(
        text='<b>3D Volumetric THz Imaging</b>', 
        font=dict(family="Arial", size=20, color="black"), 
        x=0.5 # 居中
    ),
    
    # 纯白背景：最符合排版需求
    paper_bgcolor='white',
    plot_bgcolor='white',

    scene=dict(
        # 英文坐标轴标签，科研规范 (arb. u. 或 pixel / mm)
        xaxis_title=dict(text='Y-axis (Pixel)', font=dict(family="Arial", size=14, color="black")),
        yaxis_title=dict(text='Z-axis (Depth)', font=dict(family="Arial", size=14, color="black")),
        zaxis_title=dict(text='X-axis (Pixel)', font=dict(family="Arial", size=14, color="black")),
        
        # 🎓 【边框规范】白色底板，浅灰网格线，黑色坐标轴线
        xaxis=dict(backgroundcolor="white", gridcolor="lightgrey", showbackground=True, showline=True, linecolor="black", zerolinecolor="lightgrey", tickfont=dict(color="black", family="Arial")),
        yaxis=dict(backgroundcolor="white", gridcolor="lightgrey", showbackground=True, showline=True, linecolor="black", zerolinecolor="lightgrey", tickfont=dict(color="black", family="Arial")),
        zaxis=dict(backgroundcolor="white", gridcolor="lightgrey", showbackground=True, showline=True, linecolor="black", zerolinecolor="lightgrey", tickfont=dict(color="black", family="Arial")),
        
        camera=dict(
            eye=dict(x=0, y=-2.2, z=0), # 正视角依然保留
            up=dict(x=0, y=0, z=1)
        ),
        aspectmode='data' 
    ),
    margin=dict(l=10, r=10, b=10, t=50) # 收缩多余白边，方便截图
)

# ==========================================
# 💾 5. 导出结果
# ==========================================
save_name = 'THz_3D_Academic_View.html'
fig.write_html(save_name, auto_open=True)
print(f"✅ 学术级 3D 渲染完毕！已保存至: {save_name}")
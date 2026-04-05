import h5py
import numpy as np
import matplotlib.pyplot as plt
import os

# ==========================================
# ⚙️ 1. 用户配置区
# ==========================================
filepath = "173626_THz_3D_Sample_15x20x75_P20.h5"
z_positions = [0, 40, 80, 120,160]  
step_mm = 5.0  # P50 对应的物理步长 5.0 mm

if not os.path.exists(filepath):
    raise FileNotFoundError(f"找不到文件: {filepath}")

with h5py.File(filepath, 'r') as f:
    intensity = np.abs(f['image_mean_processed'][:])

num_slices = min(len(z_positions), intensity.shape[0])
y_dim, x_dim = intensity.shape[1], intensity.shape[2]

# 物理坐标范围
extent_max_x = x_dim * step_mm
extent_max_y = y_dim * step_mm
extent = [0, extent_max_x, 0, extent_max_y]

global_max = np.max(intensity)

# ==========================================
# 🎨 2. 绘图与大小计算
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

fig, axes = plt.subplots(1, num_slices, figsize=(22, 5), facecolor='white')
fig.suptitle(f"太赫兹光斑有效大小 (50% 能量边界) | {filepath}", fontsize=20, fontweight='bold', y=1.08)

for i in range(num_slices):
    slice_2d = intensity[i]
    ax = axes[i]
    
    # 1. 计算核心物理数据
    peak_val = np.max(slice_2d)
    half_max = peak_val / 2.0  # 半高能量阈值 (50% 边界)
    
    # 计算等效直径 (数格子法，现在框够大，算得很准)
    pixels_above_hm = np.sum(slice_2d >= half_max)
    area_hm = pixels_above_hm * (step_mm ** 2)
    eq_diameter = 2 * np.sqrt(area_hm / np.pi)
    
    # 2. 绘制热力图底图
    im = ax.imshow(slice_2d, cmap='magma', origin='lower', vmin=0, vmax=global_max, extent=extent)
    
    # 3. 核心功能：在图上画出“光斑边界圈” (等高线)
    # 生成用于画等高线的网格坐标
    x_grid = np.arange(0, extent_max_x, step_mm) + step_mm / 2.0
    y_grid = np.arange(0, extent_max_y, step_mm) + step_mm / 2.0
    X, Y = np.meshgrid(x_grid, y_grid)
    
    # 画出 50% 能量的边界线 (亮青色线条)
    ax.contour(X, Y, slice_2d, levels=[half_max], colors='cyan', linewidths=2.5, linestyles='dashed')
    
    # 绘制最高点准星
    y_max_idx, x_max_idx = np.unravel_index(np.argmax(slice_2d), slice_2d.shape)
    center_x = x_max_idx * step_mm + step_mm / 2.0
    center_y = y_max_idx * step_mm + step_mm / 2.0
    ax.plot(center_x, center_y, '+', color='white', markersize=12, markeredgewidth=2)
    
    # 设置刻度
    ax.set_xticks(np.arange(0, extent_max_x + 1, 10))
    ax.set_yticks(np.arange(0, extent_max_y + 1, 10))
    ax.set_xlabel("X-Axis [mm]", fontsize=12)
    
    if i == 0:
        ax.set_ylabel("Y-Axis [mm]", fontsize=12)
    else:
        ax.set_yticklabels([]) 
        
    # 标题直接标出计算出的光斑直径
    title_str = f"Z = {z_positions[i]} mm\n光斑直径: {eq_diameter:.1f} mm\n峰值: {peak_val:.3f} V"
    ax.set_title(title_str, fontsize=13, pad=10, fontweight='bold')

# 添加 Colorbar
plt.subplots_adjust(wspace=0.1)
cbar_ax = fig.add_axes([0.91, 0.15, 0.01, 0.7])
cbar = fig.colorbar(im, cax=cbar_ax)
cbar.set_label("绝对光强 (Absolute Intensity) [V]", fontsize=14)

plt.savefig(f"Beam_Size_{filepath.replace('.h5', '.png')}", dpi=200, bbox_inches='tight', facecolor='white')
plt.show()
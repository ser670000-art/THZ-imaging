import h5py
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

# ==========================================
# ⚙️ 1. 用户配置区
# ==========================================
filepath = "161319_THz_3D_Sample_22x26x3_P20.h5"
# 仅保留前 4 个有效切面
z_positions = [200, 200, 280,300]
step_mm = 4.0   # 物理步长 4.0 mm

with h5py.File(filepath, 'r') as f:
    intensity = np.abs(f['image_mean_processed'][:])

num_slices = min(len(z_positions), intensity.shape[0])
y_dim, x_dim = intensity.shape[1], intensity.shape[2]

# 生成网格物理坐标
x_1d = np.arange(0, x_dim * step_mm, step_mm) + step_mm / 2.0
y_1d = np.arange(0, y_dim * step_mm, step_mm) + step_mm / 2.0
x_mesh, y_mesh = np.meshgrid(x_1d, y_1d)

# 定义高斯曲面方程
def gaussian_2d(xy_mesh, amp, x0, y0, sigma_x, sigma_y, offset):
    x, y = xy_mesh
    sigma_x = max(sigma_x, 1e-6)
    sigma_y = max(sigma_y, 1e-6)
    return (offset + amp * np.exp(-(((x - x0)**2)/(2 * sigma_x**2) + ((y - y0)**2)/(2 * sigma_y**2)))).ravel()

# ==========================================
# 🎨 2. 绘图与计算逻辑
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 画布宽度自适应
fig_width = max(12, num_slices * 4.5)
fig, axes = plt.subplots(1, num_slices, figsize=(fig_width, 6.5), facecolor='white')
fig.text(0.5, 0.95, f"太赫兹光束发散分析 (高斯数学半径) | 步长 4.0 mm", ha='center', va='center', fontsize=18, fontweight='bold')

# 根据前 4 层计算全局最亮值，使热力图颜色对比度更佳
global_max = np.max(intensity[:num_slices])
extent = [0, x_dim * step_mm, 0, y_dim * step_mm]

for i in range(num_slices):
    slice_2d = intensity[i]
    ax = axes[i]
    peak = np.max(slice_2d)
    
    # 50% 能量边界（仅用于画虚线框定视觉范围）
    hm = peak / 2.0
    
    # 计算 高斯拟合半径
    amp_guess = peak - np.min(slice_2d)
    y_max, x_max = np.unravel_index(np.argmax(slice_2d), slice_2d.shape)
    x0_guess, y0_guess = x_1d[x_max], y_1d[y_max]
    
    bounds = ([0, -20, -20, 1, 1, 0], [1.0, x_dim*step_mm+20, y_dim*step_mm+20, 150, 150, 0.5])
    p0 = (amp_guess, x0_guess, y0_guess, 15, 15, np.min(slice_2d))
    
    try:
        popt, _ = curve_fit(gaussian_2d, (x_mesh, y_mesh), slice_2d.ravel(), p0=p0, bounds=bounds)
        gx, gy = popt[1], popt[2]
        r_x = 2.355 * popt[3] / 2.0  # 半高全宽 (FWHM) 除以 2 得到半径
        r_y = 2.355 * popt[4] / 2.0
        fit_radius = (r_x + r_y) / 2.0
    except:
        gx, gy, fit_radius = x0_guess, y0_guess, 0.0
        
    # 绘制底图
    im = ax.imshow(slice_2d, cmap='magma', origin='lower', vmin=0, vmax=global_max, extent=extent)
    
    # 画 50% 等高线
    ax.contour(x_mesh, y_mesh, slice_2d, levels=[hm], colors='cyan', linewidths=2, linestyles='dashed')
    # 画高斯拟合中心
    ax.plot(gx, gy, 'P', color='#00FF00', markersize=10, markeredgecolor='black', label="高斯数学中心")
    
    # 精简后的标题（去掉了等效半径）
    title_str = f"Z = {z_positions[i]} mm\n光斑半径: {fit_radius:.1f} mm\n最高峰值: {peak:.3f} V"
    ax.set_title(title_str, fontsize=13, pad=12, fontweight='bold')
    
    if i == 0:
        ax.set_ylabel("Y-Axis [mm]", fontsize=12)
        ax.legend(loc='upper left', fontsize=10)
    else:
        ax.set_yticklabels([])
    
    ax.set_xlabel("X-Axis [mm]", fontsize=12)

# 右侧统一个 Colorbar
cbar_ax = fig.add_axes([0.91, 0.15, 0.012, 0.65])
fig.colorbar(im, cax=cbar_ax).set_label("绝对光强 [V]", fontsize=12)
plt.subplots_adjust(wspace=0.1)

# 保存文件
plt.savefig("Beam_Radius_Clean_Report.png", dpi=200, bbox_inches='tight', facecolor='white')
plt.show()
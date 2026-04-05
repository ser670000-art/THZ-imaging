import h5py
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

# ==========================================
# ⚙️ 1. 用户配置区 (自适应改造)
# ==========================================
filepath = "182955_THz_3D_Sample_25x30x5_P40.h5"
step_mm = 3.0       # XY 平面物理步长
z_step_mm = 20.0    # Z 轴每次前进的物理间距 (用于自动生成 Z 坐标)

if not os.path.exists(filepath):
    raise FileNotFoundError(f"找不到文件: {filepath}")

with h5py.File(filepath, 'r') as f:
    intensity = np.abs(f['image_mean_processed'][:])

# 🚀 自动读取总层数，动态生成 z_positions
num_slices = intensity.shape[0]
z_positions = [i * z_step_mm for i in range(num_slices)]

# 生成真实的物理坐标网格 (像素中心点坐标)
y_dim, x_dim = intensity.shape[1], intensity.shape[2]
x_1d = np.arange(0, x_dim * step_mm, step_mm) + step_mm / 2.0
y_1d = np.arange(0, y_dim * step_mm, step_mm) + step_mm / 2.0
x_mesh, y_mesh = np.meshgrid(x_1d, y_1d)

# ==========================================
# 🧠 2. 核心数学：2D 高斯方程定义
# ==========================================
def gaussian_2d(xy_mesh, amp, x0, y0, sigma_x, sigma_y, offset):
    """标准的二维高斯光束能量分布方程"""
    x, y = xy_mesh
    sigma_x = max(sigma_x, 1e-6)
    sigma_y = max(sigma_y, 1e-6)
    g = offset + amp * np.exp(-(((x - x0)**2)/(2 * sigma_x**2) + ((y - y0)**2)/(2 * sigma_y**2)))
    return g.ravel()

# ==========================================
# 🚀 3. 执行高斯曲面拟合 (还原真实的中心与直径)
# ==========================================
centers_x, centers_y = [], []
fwhms = []
peaks = []
slices = []

print("="*50)
print(f" 🔬 2D 高斯拟合启动 | 共检测到 {num_slices} 个数据层")
print("="*50)

for i in range(num_slices):
    slice_2d = intensity[i]
    slices.append(slice_2d)
    
    amp_guess = np.max(slice_2d) - np.min(slice_2d)
    offset_guess = np.min(slice_2d)
    y_max, x_max = np.unravel_index(np.argmax(slice_2d), slice_2d.shape)
    x0_guess = x_1d[x_max]
    y0_guess = y_1d[y_max]
    
    bounds = (
        [0, -10, -10, 1, 1, 0],
        [1.0, x_dim*step_mm + 10, y_dim*step_mm + 10, 60, 60, 0.5]
    )
    p0 = (amp_guess, x0_guess, y0_guess, 10, 10, offset_guess)
    
    try:
        popt, _ = curve_fit(gaussian_2d, (x_mesh, y_mesh), slice_2d.ravel(), p0=p0, bounds=bounds)
        amp, x0, y0, sx, sy, offset = popt
        
        centers_x.append(x0)
        centers_y.append(y0)
        
        fwhm_x = 2.355 * sx
        fwhm_y = 2.355 * sy
        true_fwhm = (fwhm_x + fwhm_y) / 2.0
        fwhms.append(true_fwhm)
        peaks.append(amp + offset)
        
        print(f"Z={z_positions[i]:<4.1f}mm | 中心: X={x0:5.1f}, Y={y0:5.1f} | FWHM: {true_fwhm:4.1f} mm | 峰值: {amp+offset:.3f} V")
    
    except Exception as e:
        print(f"Z={z_positions[i]} 拟合失败: {e}")
        # 如果拟合失败，填充默认值防止绘图报错
        centers_x.append(x0_guess); centers_y.append(y0_guess)
        fwhms.append(0.0); peaks.append(0.0)

# ==========================================
# 🤖 4. 高阶光路状态诊断逻辑 (兼顾单层与多层)
# ==========================================
print("-" * 50)
if num_slices > 1:
    dia_change = fwhms[-1] - fwhms[0]
    shift_x = centers_x[-1] - centers_x[0]
    shift_y = centers_y[-1] - centers_y[0]
    total_shift = np.sqrt(shift_x**2 + shift_y**2)

    if dia_change > 3.0 or total_shift > 3.0:
        status_text = "光束存在发散或离轴偏斜"
        status_color = "#C00000"
        detail_text = f"🔴 跨度 {z_positions[-1]-z_positions[0]}mm: 直径变化 {dia_change:+.1f} mm | 中心偏移 {total_shift:.1f} mm。"
        advice_text = "💡 建议操作：请微调透镜使首尾层中心坐标(X,Y)完全重合，然后再调整探头间距以改善发散。"
    else:
        status_text = "平行准直 (光束形态良好)"
        status_color = "#008000"
        detail_text = f"🟢 跨度 {z_positions[-1]-z_positions[0]}mm 内，能量、光斑大小与中心位置均保持稳定。"
        advice_text = "💡 建议操作：光路极其健康，无需调整！"
else:
    status_text = "单层分析模式"
    status_color = "#0284C7"
    detail_text = f"🔵 当前仅导入 1 个切面，真实直径为 {fwhms[0]:.1f} mm。"
    advice_text = "💡 建议操作：如需评估光路平行度，请设置 Z 轴步长并扫描多个层级。"

print(f"诊断结果: {status_text}")
print(detail_text)
print("="*50 + "\n")

# ==========================================
# 🎨 5. 弹性自适应绘图排版
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 动态计算画布宽度：基础宽度 + 每增加一层加 3.5 英寸
fig_width = max(12, num_slices * 3.5 + 2)
fig, axes = plt.subplots(1, num_slices, figsize=(fig_width, 6), facecolor='white')

# 解决单层数据时 axes 不是数组的报错问题
if num_slices == 1:
    axes = [axes]

# 留出顶部空间放诊断报告文字
plt.subplots_adjust(top=0.72, bottom=0.1, left=0.05, right=0.92, wspace=0.15)

fig.text(0.5, 0.93, f"太赫兹光束高斯拟合报告 | 共 {num_slices} 层", ha='center', va='center', fontsize=20, fontweight='bold')
fig.text(0.05, 0.85, f"光束诊断：{status_text}", ha='left', va='center', fontsize=16, fontweight='bold', color=status_color)
fig.text(0.05, 0.79, detail_text, ha='left', va='center', fontsize=14)

global_max = np.max(slices)
extent = [0, x_dim * step_mm, 0, y_dim * step_mm]

for i in range(num_slices):
    ax = axes[i]
    im = ax.imshow(slices[i], cmap='magma', origin='lower', vmin=0, vmax=global_max, extent=extent)
    
    # 画高斯拟合数学中心
    ax.plot(centers_x[i], centers_y[i], 'P', color='#00FF00', markersize=12, markeredgecolor='black', label="真实数学中心")
    
    ax.set_xticks(np.arange(0, x_dim*step_mm + 1, step_mm * 2))
    ax.set_yticks(np.arange(0, y_dim*step_mm + 1, step_mm * 2))
    ax.set_xlabel("X-Axis [mm]", fontsize=11)
    
    if i == 0:
        ax.set_ylabel("Y-Axis [mm]", fontsize=11)
        ax.legend(loc="upper right", fontsize=9)
    else:
        ax.set_yticklabels([]) 
    
    # 若拟合失败，FWHM 会是 0，做个规避显示
    fwhm_str = f"{fwhms[i]:.1f} mm" if fwhms[i] > 0 else "N/A"
    title_str = f"Z = {z_positions[i]:.1f} mm\n中心: ({centers_x[i]:.1f}, {centers_y[i]:.1f})\n直径: {fwhm_str}"
    ax.set_title(title_str, fontsize=12, pad=10, fontweight='bold')

# 添加统一个 Colorbar
cbar_ax = fig.add_axes([0.93, 0.1, 0.015, 0.62])
fig.colorbar(im, cax=cbar_ax).set_label("绝对光强 [V]", fontsize=12)

# 底部建议框
advice_box = patches.Rectangle((0.05, 0.02), 0.87, 0.06, transform=fig.transFigure, facecolor='#F5F5F5', edgecolor='#DDDDDD', clip_on=False)
fig.patches.append(advice_box)
fig.text(0.06, 0.05, advice_text, ha='left', va='center', fontsize=13, fontweight='bold', color='#333333')

plt.savefig("Gaussian_Report_Dynamic.png", dpi=200, bbox_inches='tight', facecolor='white')
plt.show()
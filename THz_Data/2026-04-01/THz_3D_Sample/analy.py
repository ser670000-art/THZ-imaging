import h5py
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

# ==========================================
# ⚙️ 1. 用户配置区
# ==========================================
filepath = "161319_THz_3D_Sample_22x26x3_P20.h5"
z_positions = [0, 20, 40, 60, 80]  
step_mm = 3.0                      

if not os.path.exists(filepath):
    raise FileNotFoundError(f"找不到文件: {filepath}")

with h5py.File(filepath, 'r') as f:
    intensity = np.abs(f['image_mean_processed'][:])

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
    # 防止除以 0 的极小值保护
    sigma_x = max(sigma_x, 1e-6)
    sigma_y = max(sigma_y, 1e-6)
    # 高斯曲面计算公式
    g = offset + amp * np.exp(-(((x - x0)**2)/(2 * sigma_x**2) + ((y - y0)**2)/(2 * sigma_y**2)))
    return g.ravel() # scipy 拟合要求返回一维数组

# ==========================================
# 🚀 3. 执行高斯曲面拟合 (还原真实的中心与直径)
# ==========================================
centers_x, centers_y = [], []
fwhms = []
peaks = []
slices = []

print("="*50)
print(" 🔬 2D 高斯拟合物理指标提取 (突破截断误差)")
print("="*50)

for i in range(len(z_positions)):
    slice_2d = intensity[i]
    slices.append(slice_2d)
    
    # 获取初步的猜测值 (提高拟合成功率)
    amp_guess = np.max(slice_2d) - np.min(slice_2d)
    offset_guess = np.min(slice_2d)
    y_max, x_max = np.unravel_index(np.argmax(slice_2d), slice_2d.shape)
    x0_guess = x_1d[x_max]
    y0_guess = y_1d[y_max]
    
    # 限制高斯拟合的边界，防止算出反人类的数据
    bounds = (
        [0, -10, -10, 1, 1, 0], # 下限：允许中心点跑到相框外 (-10mm)
        [1.0, x_dim*step_mm + 10, y_dim*step_mm + 10, 60, 60, 0.5] # 上限
    )
    p0 = (amp_guess, x0_guess, y0_guess, 10, 10, offset_guess)
    
    try:
        # 核心算力：使用非线性最小二乘法进行曲面拟合
        popt, _ = curve_fit(gaussian_2d, (x_mesh, y_mesh), slice_2d.ravel(), p0=p0, bounds=bounds)
        amp, x0, y0, sx, sy, offset = popt
        
        # 记录真实的几何中心
        centers_x.append(x0)
        centers_y.append(y0)
        
        # 计算高斯半高全宽 FWHM = 2.355 * sigma
        fwhm_x = 2.355 * sx
        fwhm_y = 2.355 * sy
        true_fwhm = (fwhm_x + fwhm_y) / 2.0 # 取平均直径
        fwhms.append(true_fwhm)
        peaks.append(amp + offset)
        
        print(f"Z={z_positions[i]:<2}mm | 真实中心: X={x0:.1f}, Y={y0:.1f} | 真实 FWHM: {true_fwhm:.1f} mm | 理论峰值: {amp+offset:.3f} V")
    
    except Exception as e:
        print(f"Z={z_positions[i]} 拟合失败: {e}")

# ==========================================
# 🤖 4. 高阶光路状态诊断逻辑
# ==========================================
print("-" * 50)
dia_change = fwhms[-1] - fwhms[0]
shift_x = centers_x[-1] - centers_x[0]
shift_y = centers_y[-1] - centers_y[0]
total_shift = np.sqrt(shift_x**2 + shift_y**2)

if dia_change > 3.0:
    status_text = "光束严重发散 且 离轴偏斜"
    status_color = "#C00000"
    detail_text = f"🔴 经过 {z_positions[-1]}mm，真实直径暴涨了 {dia_change:.1f} mm！\n🔴 光斑中心偏移了 {total_shift:.1f} mm (X移 {shift_x:.1f}, Y移 {shift_y:.1f})。"
    advice_text = "💡 建议操作：1.先左右上下微调透镜，使Z=0和Z=80的中心坐标(X,Y)完全重合。\n2.然后再将太赫兹源向后退，解决发散问题。"
else:
    status_text = "平行准直"
    status_color = "#008000"
    detail_text = "🟢 能量与光斑大小保持稳定。"
    advice_text = "💡 建议操作：无需调整。"

print(f"诊断结果: {status_text}")
print(detail_text.replace('\n', ' '))
print("="*50 + "\n")

# ==========================================
# 🎨 5. 绘图 (带真实中心标注)
# ==========================================
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

fig = plt.figure(figsize=(22, 7.5), facecolor='white')
fig.text(0.5, 0.92, "太赫兹光束高斯曲面拟合诊断报告 (Gaussian Fit Report)", ha='center', va='center', fontsize=22, fontweight='bold')
fig.text(0.04, 0.84, f"当前光束状态：{status_text}", ha='left', va='center', fontsize=18, fontweight='bold', color=status_color)
fig.text(0.04, 0.77, detail_text, ha='left', va='center', fontsize=15)

global_max = np.max(slices)
extent = [0, x_dim * step_mm, 0, y_dim * step_mm]

for i in range(len(z_positions)):
    ax = fig.add_axes([0.04 + i * 0.174, 0.22, 0.15, 0.45]) 
    im = ax.imshow(slices[i], cmap='magma', origin='lower', vmin=0, vmax=global_max, extent=extent)
    
    # 🎯 这里画的是高斯方程算出来的【真实物理中心】，而不是相框里最亮的点！
    ax.plot(centers_x[i], centers_y[i], 'P', color='#00FF00', markersize=12, markeredgecolor='black', label="真实数学中心")
    
    ax.set_xticks(np.arange(0, x_dim*step_mm + 1, 3))
    ax.set_yticks(np.arange(0, y_dim*step_mm + 1, 3))
    ax.set_xlabel("X-Axis [mm]", fontsize=11)
    if i == 0:
        ax.set_ylabel("Y-Axis Position [mm]", fontsize=11)
        ax.legend(loc="upper right", fontsize=9)
    else:
        ax.set_yticklabels([]) 
    
    title_str = f"Z = {z_positions[i]} mm\n拟合中心: ({centers_x[i]:.1f}, {centers_y[i]:.1f})\n真实直径: {fwhms[i]:.1f} mm"
    ax.set_title(title_str, fontsize=12, pad=12, fontweight='bold')

cbar_ax = fig.add_axes([0.915, 0.22, 0.01, 0.45])
fig.colorbar(im, cax=cbar_ax).set_label("绝对光强 (Absolute Intensity) [V]", fontsize=12)

advice_box = patches.Rectangle((0.04, 0.05), 0.885, 0.08, transform=fig.transFigure, facecolor='#F5F5F5', edgecolor='#DDDDDD')
fig.patches.append(advice_box)
fig.text(0.05, 0.09, advice_text, ha='left', va='center', fontsize=13, fontweight='bold', color='#333333')

plt.savefig("Gaussian_Report.png", dpi=200, bbox_inches='tight', facecolor='white')
plt.show()
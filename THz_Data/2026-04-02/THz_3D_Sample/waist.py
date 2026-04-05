import numpy as np
import h5py
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# ==========================================
# 1. 参数设置
# ==========================================
file_path = '182955_THz_3D_Sample_25x30x5_P40.h5'
pixel_size_mm = 2.0  # 你的真实步长 2mm

# 假设诊断第一层 (Z=3.5)
slice_index = 0  

# ==========================================
# 2. 核心算法：二维高斯曲面拟合
# ==========================================
def gaussian_2d(M, amplitude, xo, yo, sigma_x, sigma_y, offset):
    """标准的 2D 高斯模型"""
    x, y = M
    g = offset + amplitude * np.exp( - (((x - xo)**2) / (2 * sigma_x**2) + ((y - yo)**2) / (2 * sigma_y**2)) )
    return g.ravel()

# 读取并清理数据
with h5py.File(file_path, 'r') as f:
    dataset_name = list(f.keys())[0]
    intensity_3d = np.array(f[dataset_name])
    if intensity_3d.shape[-1] <= 10: 
        intensity_3d = np.transpose(intensity_3d, (2, 0, 1))
    data_2d = intensity_3d[slice_index]

# 去底噪
bg = np.mean(np.concatenate([data_2d[0,:], data_2d[-1,:], data_2d[:,0], data_2d[:,-1]]))
data_2d = data_2d - bg
data_2d[data_2d < 0] = 0

# 生成真实的 X, Y 物理坐标网格 (单位: mm)
y_dim, x_dim = data_2d.shape
x_mm = np.arange(x_dim) * pixel_size_mm
y_mm = np.arange(y_dim) * pixel_size_mm
X, Y = np.meshgrid(x_mm, y_mm)

# 给出拟合的初始猜测值
max_val = np.max(data_2d)
y_max, x_max = np.unravel_index(np.argmax(data_2d), data_2d.shape)
guess = (max_val, x_max * pixel_size_mm, y_max * pixel_size_mm, 10.0, 10.0, 0.0)

# 执行二维拟合
popt, pcov = curve_fit(gaussian_2d, (X, Y), data_2d.ravel(), p0=guess)
amplitude, x0_fit, y0_fit, sigma_x, sigma_y, offset = popt

# 提取拟合标准差 (用于误差分析)
perr = np.sqrt(np.diag(pcov))
err_sigma_x = perr[3]
err_sigma_y = perr[4]

# 换算为 1/e^2 物理半径 (w = 2 * sigma)
w_x = 2 * abs(sigma_x)
w_y = 2 * abs(sigma_y)
w_mean = (w_x + w_y) / 2

err_w_x = 2 * err_sigma_x
err_w_y = 2 * err_sigma_y
err_w_mean = (err_w_x + err_w_y) / 2

print("="*50)
print(f"📊 步长 {pixel_size_mm}mm 下的光斑二维拟合误差分析")
print("="*50)
print(f"亚像素真实中心坐标 : X = {x0_fit:.2f} mm, Y = {y0_fit:.2f} mm")
print(f"消除离散误差后的光斑半径 w : {w_mean:.2f} mm")
print(f"拟合系统误差范围 (95%置信度): ± {err_w_mean * 1.96:.2f} mm")
print("="*50)

# ==========================================
# 3. 诊断绘图 (实测网格 vs 拟合平滑曲面)
# ==========================================
plt.figure(figsize=(10, 4), dpi=120)
plt.rcParams.update({"font.family": "serif"})

# 实测粗糙图
ax1 = plt.subplot(1, 2, 1)
ax1.imshow(data_2d, origin='lower', extent=[0, x_mm[-1], 0, y_mm[-1]], cmap='magma')
ax1.set_title(f'Measured Coarse Data ({pixel_size_mm}mm step)')
ax1.set_xlabel('X (mm)')
ax1.set_ylabel('Y (mm)')

# 拟合平滑图
ax2 = plt.subplot(1, 2, 2)
fit_surface = gaussian_2d((X, Y), *popt).reshape(y_dim, x_dim)
ax2.imshow(fit_surface, origin='lower', extent=[0, x_mm[-1], 0, y_mm[-1]], cmap='magma')
ax2.contour(X, Y, fit_surface, levels=[offset + amplitude * 0.135], colors='g', linestyles='--') # 1/e^2 线
ax2.set_title(f'Fitted Smooth Surface (w = {w_mean:.2f}±{err_w_mean:.2f} mm)')
ax2.set_xlabel('X (mm)')

plt.tight_layout()
plt.show()
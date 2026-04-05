import h5py
import numpy as np
import matplotlib.pyplot as plt
import os

# ==========================================
# ⚙️ 1. 用户配置区
# ==========================================
# 请填入你刚刚扫完的 H5 文件名
filepath = "175757_THz_3D_Sample_7x7x3_P30.h5"

# 扫描时的物理参数 (依据你的设定修改)
z_positions = [0, 15, 45]  # 三个截面的实际 Z 坐标 (mm)
step_mm = 3.0              # 你的 P30 扫描步长 (mm)

# ==========================================
# 🧠 2. 数据读取与几何物理计算
# ==========================================
def analyze_beam_propagation(file_path):
    if not os.path.exists(file_path):
        print(f"❌ 找不到文件: {file_path}")
        return

    with h5py.File(file_path, 'r') as f:
        # 取绝对值，兼容锁相放大器的负电压现象
        intensity = np.abs(f['image_mean_processed'][:])

    z_len = intensity.shape[0]
    if z_len != 3:
        print(f"⚠️ 警告：该文件包含 {z_len} 层数据，而非预期的 3 层。程序将取前 3 层。")

    peaks = []
    diameters = []
    slices = []

    # 遍历 3 层 Z 切片
    for i in range(3):
        slice_2d = intensity[i]
        slices.append(slice_2d)
        
        # 1. 提取中心最高光强
        peak = np.max(slice_2d)
        peaks.append(peak)
        
        # 2. 计算等效直径 (解决 7x7 分辨率过低无法直接量 FWHM 的问题)
        # 统计能量大于峰值 50% 的像素点个数
        half_max = peak / 2.0
        pixels_above_hm = np.sum(slice_2d >= half_max)
        
        # 将像素数转化为真实的物理面积，再反推等效圆直径: D = 2 * sqrt(Area / pi)
        pixel_area = step_mm * step_mm
        area_hm = pixels_above_hm * pixel_area
        equivalent_diameter = 2 * np.sqrt(area_hm / np.pi)
        diameters.append(equivalent_diameter)

    # ==========================================
    # 🤖 3. 光路自动诊断专家系统
    # ==========================================
    print("\n" + "="*50)
    print(" 🚀 太赫兹光束传播状态自动诊断报告")
    print("="*50)
    
    for i in range(3):
        print(f"Z = {z_positions[i]:<2} mm | 峰值能量: {peaks[i]:.4f} V | 等效直径: {diameters[i]:.2f} mm")
        
    print("-" * 50)
    
    # 诊断逻辑：比较末端(Z=45)与前端(Z=0)的直径变化
    dia_change_ratio = diameters[2] / diameters[0]
    peak_change_ratio = peaks[2] / peaks[0]
    
    if dia_change_ratio > 1.05 and peak_change_ratio < 0.95:
        diagnosis = "🔴 【发散 (Diverging)】"
        advice = "光斑在扩大，能量在减弱。说明太赫兹源距离准直透镜【太近】。请将发射头向后微调（远离透镜）。"
    elif dia_change_ratio < 0.95 and peak_change_ratio > 1.05:
        diagnosis = "🔵 【汇聚 (Converging)】"
        advice = "光斑在缩小，能量在集中。说明太赫兹源距离准直透镜【太远】。请将发射头向前微调（靠近透镜）。"
    else:
        diagnosis = "🟢 【平行准直 (Parallel/Collimated)】"
        advice = "光斑大小和能量基本保持恒定，准直透镜焦距调节得非常完美！"
        
    print(f"光束状态: {diagnosis}")
    print(f"调光建议: {advice}")
    print("="*50 + "\n")

    # ==========================================
    # 🎨 4. 绘制光斑对比热力图
    # ==========================================
    plt.rcParams['font.sans-serif'] = ['SimHei'] # 支持中文
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.suptitle(f"太赫兹光束 3D 演化图 ({diagnosis})", fontsize=16, fontweight='bold')

    # 强制三张图使用统一的颜色尺，直观体现能量衰减
    global_max = max(peaks)
    
    for i in range(3):
        ax = axes[i]
        im = ax.imshow(slices[i], cmap='magma', origin='lower', vmin=0, vmax=global_max)
        ax.set_title(f"Z = {z_positions[i]} mm\nPeak: {peaks[i]:.3f} V | Dia: {diameters[i]:.1f} mm", fontsize=11)
        ax.axis('off') # 关闭坐标轴使光斑更清晰
        
    # 添加全局 Colorbar
    cbar_ax = fig.add_axes([0.92, 0.15, 0.015, 0.7])
    fig.colorbar(im, cax=cbar_ax, label="绝对光强 (V)")
    
    plt.subplots_adjust(left=0.05, right=0.9, wspace=0.1)
    plt.savefig("Beam_Diagnostics.png", dpi=150)
    plt.show()

# 运行程序
analyze_beam_propagation(filepath)
import numpy as np
import warnings

print("🧠 数字信号处理引擎已加载:")

class THzSignalProcessor:
    """
    太赫兹单像素成像：数字信号处理核心 (DSP)
    负责对 DAQ 采集到的高频一维时域信号进行降噪、去极值与特征提取。
    """
    def __init__(self, clip_percentile=5.0):
        """
        初始化算法
        hampel滤波
        :param clip_percentile: 极值切除比例。默认 5.0，意味着砍掉最高 5% 和最低 5% 的毛刺，保留核心 90% 的数据。
        """
        self.clip_p = clip_percentile
        
        # 参数合法性校验
        if self.clip_p < 0 or self.clip_p >= 50:
            raise ValueError("过滤百分比必须在 0 到 50 之间！")

    def process_pixel(self, raw_samples):
        """
        处理单个像素点的原始波形数据
        :param raw_samples: list 或 np.array, 包含该点采集的 N 个电压值 (如 1000 个点)
        :return: (raw_mean, proc_mean, proc_samples) 🎯 必须返回 3 个值！
        """
        # 1. 高效数据转换
        arr = np.asarray(raw_samples, dtype=np.float64)
        
        # ==========================================
        # 第一道步：硬件毒数据与空数据拦截
        # ==========================================
        if arr.size == 0 or arr[0] == -999.0:
            # 🎯 必须返回 3 个空值（第三个为空数组），防止 UI 绘图崩溃
            return np.nan, np.nan, np.array([])

        # ==========================================
        # 第二步：提取原始基准数据 (处理前)
        # ==========================================
        raw_mean = np.mean(arr)

        # ==========================================
        # 🛡️ 第三步：自适应hampel滤波 (处理后)
        # ==========================================
        # 优化点 1：如果数据本身非常纯净平滑（标准差极小），直接跳过滤波
        if np.std(arr) < 1e-6:
            # 极端平滑时，不需要修剪波形，直接原样返回 arr
            return float(raw_mean), float(raw_mean), arr

        # 优化点 2：动态计算统计学分位数区间 (比如 5% ~ 95%)
        p_low = np.percentile(arr, self.clip_p)
        p_high = np.percentile(arr, 100.0 - self.clip_p)
        
        # 优化点 3：利用 NumPy 的布尔掩码进行极速过滤，求出纯净均值
        valid_mask = (arr >= p_low) & (arr <= p_high)
        valid_data = arr[valid_mask]
        
        # 利用 np.clip 将超过阈值的“尖峰毛刺”强制削平
        # 这样生成的 proc_samples 发给前端后，你就能在 UI 的第二张图里看到“被修剪过”的平滑波形！
        proc_samples = np.clip(arr, p_low, p_high)
        
        # 优化点 4：极端分布保护
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            
            if valid_data.size > 0:
                proc_mean = np.mean(valid_data)
            else:
                proc_mean = raw_mean
                
        # 强制转换为标准的 Python 类型，完美对接 scan_engine
        return float(raw_mean), float(proc_mean), proc_samples
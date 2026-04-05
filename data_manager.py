import h5py
import numpy as np
import os
import time

class THzDataManager:
    def __init__(self, sample_name, x_steps, y_steps, z_steps, step_size, samples_per_pixel, base_dir="./THz_Data", existing_file=None):
        self.x_steps = x_steps
        self.y_steps = y_steps
        self.z_steps = z_steps
        self.is_closed = False
        self.h5_file = None

        try:
            # 🟢 模式 A：修补/续扫模式
            if existing_file and os.path.exists(existing_file):
                self.h5_path = existing_file
                self.target_dir = os.path.dirname(existing_file)
                
                # ⚠️ 必须用 'a' 模式，允许读写且不截断原文件
                self.h5_file = h5py.File(self.h5_path, 'a')
                
                # 绑定数据集引用
                self.ds_raw = self.h5_file["raw_data"]
                self.ds_mean_raw = self.h5_file["image_mean_raw"]
                self.ds_mean_proc = self.h5_file["image_mean_processed"]
                print(f"🔧 [数据引擎] 开启修补模式，成功加载现有文件: {self.h5_path}")
                
            # 🔵 模式 B：全新扫描模式
            else:
                date_str = time.strftime("%Y-%m-%d")
                self.target_dir = os.path.join(base_dir, date_str, sample_name)
                os.makedirs(self.target_dir, exist_ok=True) # 使用 exist_ok 防止多线程创建报错
                    
                timestamp = time.strftime("%H%M%S")
                # 文件名中包含步长信息，方便以后追溯
                file_base = f"{timestamp}_{sample_name}_{x_steps}x{y_steps}x{z_steps}_P{str(step_size).replace('.','')}"
                self.h5_path = os.path.join(self.target_dir, f"{file_base}.h5")
                
                # 用 'w' 模式创建新文件
                self.h5_file = h5py.File(self.h5_path, 'w')
                
                # 预分配连续的磁盘空间
                self.ds_raw = self.h5_file.create_dataset("raw_data", (z_steps, y_steps, x_steps, samples_per_pixel), dtype='f4', compression="gzip")
                self.ds_mean_raw = self.h5_file.create_dataset("image_mean_raw", (z_steps, y_steps, x_steps), dtype='f4')
                self.ds_mean_proc = self.h5_file.create_dataset("image_mean_processed", (z_steps, y_steps, x_steps), dtype='f4')
                print(f"🚀 [数据引擎] 开启全新扫描，预分配空间完成: {self.h5_path}")

        except Exception as e:
            print(f"❌ [数据引擎] 文件初始化致命错误: {e}")
            self.is_closed = True
            raise e

    def write_pixel(self, z_idx, x_idx, y_idx, raw_samples, raw_mean, proc_mean):
        """严谨写入：带有状态锁与异常捕捉"""
        if self.is_closed or self.h5_file is None:
            return
            
        try:
            # 写入三个维度的数据
            self.ds_raw[z_idx, y_idx, x_idx, :] = raw_samples
            self.ds_mean_raw[z_idx, y_idx, x_idx] = raw_mean
            self.ds_mean_proc[z_idx, y_idx, x_idx] = proc_mean
            
            # 🛡️ 核心护航：强制刷新缓存到硬盘，抗击断电风险
            self.h5_file.flush() 
        except Exception as e:
            print(f"⚠️ [数据引擎] 像素点写入失败 (Z:{z_idx}, Y:{y_idx}, X:{x_idx}): {e}")

    def close_and_export(self):
        """带有双重保护的安全封盘机制，防止重复关闭"""
        if not self.is_closed and self.h5_file is not None:
            try:
                self.h5_file.close()
                self.is_closed = True
                print(f"📁 [数据引擎] HDF5 文件已安全封盘闭合。")
                print(f"📍 路径: {self.h5_path}")
            except Exception as e:
                print(f"⚠️ [数据引擎] 文件封盘时发生异常 (可能已断开): {e}")
# 太赫兹超高速高分辨三维层析成像系统

**(THz Ultra-High-Speed 3D Tomography System)**

本项目是一套为太赫兹（THz）无损检测与高分辨三维成像量身定制的上位机控制系统。基于 **Client-Server 分布式架构**，完美融合了底层 C/C++ 运动控制驱动与高性能数据采集，突破了传统“走走停停”扫描模式的速度瓶颈，实现了真正意义上的\*\*“连续飞点扫描（On-the-fly Scanning）”\*\*。

## ✨ 核心特性 (Core Features)

  * **🚀 超高速飞点扫描引擎 (On-the-fly Scanning)**
    抛弃低效的点位停留，通过精确计算“起跑缓冲 (Overshoot)”，电机在扫描区保持绝对匀速狂飙。结合 NI 采集卡的极高采样率，实现“时间换空间”的完美映射，扫描速度提升 10 倍以上。
  * **🧠 边缘计算与空间降维 (Edge Computing Binning)**
    在底层硬件服务器中就地处理海量 DAQ 数据。利用 NumPy 将数以十万计的冗余采样点瞬间切片并求均值，将网络通信开销和 UI 渲染压力降低三个数量级，极大提升信噪比（SNR）。
  * **🕸️ CS 进程隔离架构 (Client-Server Isolation)**
    利用 XML-RPC 搭建本地微服务，将极易卡死的“底层硬件轮询”与“UI 前端渲染”物理隔离。哪怕 UI 线程因为大数据量渲染卡顿，底层的 1ms 硬件定时器也绝不掉帧。
  * **🤖 Z 轴绝对光强自动寻峰 (Auto-Focus)**
    内置智能雷达算法，自动在指定 Z 轴范围内寻找太赫兹信号的绝对峰值（支持处理负向电压峰值），实现一键自动对焦。
  * **🎢 工业级连续流轨迹支持 (Stream Path Interpolation)**
    底层硬件库已深度破解并封装 `MT_Set_Stream` 连续轨迹插补 API，支持未来升级无减速的“圆弧平滑过弯”功能。

-----

## 🏗️ 系统架构 (Architecture)

系统由三个核心进程/模块组成：

1.  **`hardware_server.py` (硬件微服务后端)**
      * 直接对接 `MT_API.dll` 控制 CCM 滑台与雷赛步进电机。
      * 直接对接 `nidaqmx` 控制 NI USB-6211 采集卡。
      * 运行在本地 8000 端口，提供微秒级硬件控制与边缘计算服务。
2.  **`scan_engine.py` (扫描逻辑中枢)**
      * 包含核心的 `ScanThread`，负责计算复杂的 3D 贪吃蛇运动轨迹、加减速缓冲段，并处理网络调度和 HDF5 数据落盘。
3.  **`main_ui.py` (全景指挥舱前端)**
      * 采用 PyQt5 + PyQtGraph 打造的深色工业风 UI。提供双通道波形监视、实时 3D 切片更新以及紧急制动等交互功能。

-----

## 🛠️ 硬件依赖 (Hardware Requirements)

  * **太赫兹源/探测器**: VDI WR10 频段探测系统（或同级别检波器）。
  * **数据采集卡**: NI USB-6211 (National Instruments), 16-bit, 250 kS/s。
  * **机械滑台**: 广东 CCM W 系列高精度静音滑台模组。
  * **电机与驱动**:
      * X 轴: 雷赛 57CME23 (闭环步进) + CL57 驱动器。
      * Y/Z 轴: 雷赛 57HS21A (开环步进) + DM542 驱动器。

-----

## 💻 环境配置 (Installation)

1.  **安装 Python 环境** (推荐使用 Anaconda，Python 3.8 或更高版本)。
2.  **安装核心依赖库**:
    ```bash
    pip install PyQt5 pyqtgraph numpy h5py nidaqmx pefile
    ```
3.  **安装 NI 官方驱动**:
    请前往 NI 官网下载并安装 **NI-DAQmx** 驱动程序，确保在 Windows 搜索栏中能打开 `NI MAX` 软件，并能识别到采集卡。
4.  **底层驱动环境**:
    确保项目根目录下存在运动控制器的官方动态链接库 `MT_API.dll`。

-----

## 🚀 快速启动 (Quick Start)

由于系统采用前后端分离架构，**必须先启动硬件服务器，再启动 UI 界面**。

**步骤 1：启动硬件底层微服务**
打开终端，运行：

```bash
python hardware_server.py
```

*(若看到 "🔌 多线程 XML-RPC 服务已在 8000 端口启动" 且无报错，则说明硬件挂载成功。)*

**步骤 2：启动全景指挥界面**
打开新的终端，运行：

```bash
python main_ui.py
```

**步骤 3：开始扫描**
在 UI 界面中配置好 X/Y 步数和物理步长，确认太赫兹光路畅通，点击【启动高精三维层析】即可体验飞点扫描。

-----

## ⚙️ 配置文件 (`scan_config.json`)

系统的大量机械动力学参数和扫描偏好通过 JSON 热加载，重要参数说明如下：

  * `hardware_motor.pulse_ratio_k`: 脉冲当量 (默认 22.13)，即电机走 1mm 需要的脉冲数。
  * `hardware_motor.v_start_pulses`: 运动初速度。
  * `delays_s`: 物理避震延时字典，包含换层 (`layer`)、换行 (`line`) 等阶段的毫秒级等待时间，用于消除机械余震。
  * `hardware_daq.samples_per_pixel`: 在飞点扫描模式下，每个物理像素空间内**期望**采集的原始点数（系统会根据速度自动推算实际所需采样率）。

-----

## 🔮 未来进化方向 (TODOs)

  - [ ] **硬件级触发 (Hardware PSO)**：通过飞线连接 CL57 驱动器的同步输出端与 NI 卡的 PFI 0 引脚，彻底消除 Python 软件计时带来的微小网络延迟，实现真正的“零错位”绝对空间同步。
  - [ ] **圆滑过渡 (Blending Motion)**：在前端放开对 `hardware_server.py` 中 `test_smooth_snake_trajectory` 的调用，利用底层的 Stream 模式实现无停车过弯，进一步压缩 30% 机械耗时。
  - [ ] **数字锁相 (Digital Lock-in)**：引入硬件光学斩波器，在 `signal_processor.py` 中增加数字 DSP 锁相放大算法，大幅压制 1/f 噪声。

-----

*Developed by lww超快课题组.*

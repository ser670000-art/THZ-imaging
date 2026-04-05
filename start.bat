@echo off
:: 设置字符集为 UTF-8，防止中文乱码
chcp 65001 >nul
title 太赫兹 3D 扫描系统 - 启动器

echo ======================================================
echo  🚀 欢迎使用 太赫兹 3D 扫描指挥中心 一键启动引擎
echo ======================================================
echo.

:: 1. 强制切换到你的工作大本营
echo [1/3] 正在进入工程目录...
cd /d "C:\Users\li130\Desktop\THZ-project3"

:: 2. 在全新的终端窗口启动 32 位硬件服务端
echo [2/3] 正在唤醒 32位 硬件控制服务端...
start "硬件服务端 (Hardware Server)" py -V:3.14-32 hardware_server.py

:: 💡 贴心设计：让程序先等 2 秒钟。确保服务端完全启动并绑定好端口，防止 UI 瞬间启动连不上报错。
timeout /t 2 /nobreak >nul

:: 3. 在独立的终端窗口启动主控 UI
echo [3/3] 正在启动主控 UI 界面...
start "主控总舱 (Main UI)" py main_ui.py

echo.
echo ✅ 所有系统已成功拉起！本启动窗口将在 3 秒后自动关闭...
timeout /t 3 /nobreak >nul
exit
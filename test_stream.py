import xmlrpc.client

# 连接底层硬件服务
hw = xmlrpc.client.ServerProxy("http://127.0.0.1:8000/")

try:
    print("准备发送连续轨迹数据流...")
    # 参数: X轴扫20mm, Y轴每次走1mm, 扫5行, 速度5mm/s, 脉冲比22.13
    # 这一句指令发过去，Python就会进入等待，此时观察机床的物理运动！
    hw.test_smooth_snake_trajectory(20.0, 1.0, 5, 5.0, 22.13)
    print("轨迹测试圆满完成！")
except Exception as e:
    print(f"发生错误: {e}")
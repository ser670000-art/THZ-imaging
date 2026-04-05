from PIL import Image

# 1. 读取你下载的高清原图（注意这里换成你实际的图片名字，比如 icon.png）
img_path = 'THZ.png' 

try:
    img = Image.open(img_path)
    
    # 2. 强制转换并保存为 Windows 绝对认可的真 .ico 格式，包含多个尺寸
    icon_sizes = [(256, 256), (128, 128), (64, 64), (32, 32)]
    img.save('True_Icon.ico', format='ICO', sizes=icon_sizes)
    
    print("✅ 锻造成功！真正的 True_Icon.ico 已经生成在当前文件夹下！")
except Exception as e:
    print(f"❌ 失败了: {e}")
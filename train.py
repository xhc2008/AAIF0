import os
import time
import threading
import keyboard
from PIL import ImageGrab
import pygetwindow as gw
import ctypes  # 新增：用于获取系统DPI缩放

# 配置参数
MIN_INTERVAL = 0.0  # 最小截图间隔（秒），0表示无间隔
BASE_DIR = "data"   # 存储根目录
TARGET_WINDOW_TITLE = "Minecraft"  # 目标窗口标题

# 全局变量
pressed_keys = set()
last_capture_time = 0
lock = threading.Lock()
window_rect = None
window_found = False
scaling_factor = 1.15  # 屏幕缩放因子

def get_system_scaling():
    """获取系统DPI缩放比例"""
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        hdc = user32.GetDC(0)
        LOGPIXELSX = 88
        scale = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX) / 96.0
        user32.ReleaseDC(0, hdc)
        #return scale
        return 1.0
    except:
        return 1.0

def find_target_window():
    """查找目标窗口并获取其位置和大小（考虑DPI缩放）"""
    global window_rect, window_found, scaling_factor
    
    try:
        windows = gw.getWindowsWithTitle(TARGET_WINDOW_TITLE)
        if windows:
            target_window = windows[0]
            
            if target_window.isMinimized:
                target_window.restore()
                time.sleep(0.1)
            
            # 获取系统缩放比例
            scaling_factor = get_system_scaling()
            
            # 调整窗口坐标和大小（考虑DPI缩放）
            left = int(target_window.left * scaling_factor)
            top = int(target_window.top * scaling_factor)
            width = int(target_window.width * scaling_factor)
            height = int(target_window.height * scaling_factor)
            
            window_rect = (left, top, left + width, top + height)
            window_found = True
            print(f"找到目标窗口: {TARGET_WINDOW_TITLE}, 位置: {window_rect}")
            print(f"系统缩放比例: {scaling_factor:.2f}")
            return True
        else:
            print(f"未找到标题包含 '{TARGET_WINDOW_TITLE}' 的窗口")
            window_found = False
            return False
    except Exception as e:
        print(f"查找窗口出错: {e}")
        window_found = False
        return False

def capture_window():
    """截取目标窗口内容（考虑DPI缩放）"""
    global window_rect, window_found
    
    if window_rect is None or not window_found:
        if not find_target_window():
            return None
    
    try:
        return ImageGrab.grab(bbox=window_rect)
    except Exception as e:
        print(f"截图失败: {e}")
        window_found = False
        return None

def save_screenshot(img, timestamp):
    """将截图保存到按键对应目录"""
    for key in list(pressed_keys):
        key_name = key.upper() if len(key) > 1 else key
        dir_path = os.path.join(BASE_DIR, key_name)
        os.makedirs(dir_path, exist_ok=True)
        
        filename = f"{timestamp}.png"
        filepath = os.path.join(dir_path, filename)
        img.save(filepath)

def handle_key_event():
    """处理按键事件的截图逻辑"""
    global last_capture_time
    
    current_time = time.time()
    if current_time - last_capture_time < MIN_INTERVAL:
        return
    
    screenshot = capture_window()
    if screenshot is None:
        return
    
    timestamp = str(int(time.time() * 1000))
    save_screenshot(screenshot, timestamp)
    last_capture_time = current_time

def key_press_handler(event):
    """按键按下事件处理"""
    global pressed_keys
    
    with lock:
        if event.name not in pressed_keys:
            pressed_keys.add(event.name)
            handle_key_event()
            pressed_keys.remove(event.name)  # 立即移除，避免重复截图

def key_release_handler(event):
    """按键释放事件处理"""
    with lock:
        if event.name in pressed_keys:
            pressed_keys.remove(event.name)

def background_capture():
    """后台线程：持续检查按键状态并截图"""
    last_window_check = time.time()
    
    while True:
        current_time = time.time()
        if current_time - last_window_check > 5.0:
            find_target_window()
            last_window_check = current_time
        
        with lock:
            if pressed_keys:
                handle_key_event()
        
        time.sleep(max(MIN_INTERVAL, 0.01))

def main():
    print("注意：此程序需要安装以下依赖：")
    print("pip install pygetwindow pillow keyboard")
    
    os.makedirs(BASE_DIR, exist_ok=True)
    find_target_window()
    
    keyboard.on_press(key_press_handler)
    keyboard.on_release(key_release_handler)
    
    threading.Thread(target=background_capture, daemon=True).start()
    
    print(f"截图程序已启动 (目标窗口: '{TARGET_WINDOW_TITLE}')")
    print("按Ctrl+C退出...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n程序已退出")

if __name__ == "__main__":
    main()
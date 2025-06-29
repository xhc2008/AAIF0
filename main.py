import os
import cv2
import time
import numpy as np
import keyboard
from PIL import ImageGrab, Image
import threading
import atexit
import queue
from sklearn.neighbors import NearestNeighbors
import pygetwindow as gw
import pyautogui

# 配置参数
SIMILARITY_THRESHOLD = 0.75  # 匹配相似度阈值
MAX_KEYS_TO_PRESS = 1        # 一次最多模拟的按键数量
SCREENSHOT_INTERVAL = 0.05   # 截图间隔（秒）
FEATURE_EXTRACT_INTERVAL = 60  # 特征提取间隔（秒）
BASE_DIR = "data"            # 存储按键图片的目录
TARGET_WINDOW_TITLE = "Minecraft"  # 目标窗口标题

# 方向键映射表
DIRECTION_KEY_MAPPING = {
    'UP': 'up',
    'DOWN': 'down',
    'LEFT': 'left',
    'RIGHT': 'right'
}

# 全局变量
key_images = {}              # 存储按键名称和对应图片的特征向量
key_name_mapping = {}        # 按键名称映射（目录名 -> 实际按键名）
currently_pressed = set()    # 当前模拟按下的按键
nn_model = None              # 最近邻模型
lock = threading.Lock()      # 线程锁
task_queue = queue.Queue()   # 任务队列
window_rect = None           # 目标窗口位置和大小
window_found = False         # 是否找到目标窗口
last_feature_load_time = 0   # 上次加载特征的时间

def exit_handler():
    """程序退出时释放所有按键"""
    print("\n释放所有按键并退出...")
    with lock:
        for key in currently_pressed:
            try:
                actual_key = key_name_mapping.get(key, key)
                keyboard.release(actual_key)
                print(f"释放按键: {key}")
            except:
                pass
    print("程序已安全退出")

atexit.register(exit_handler)

def find_target_window():
    """查找目标窗口并获取其位置和大小"""
    global window_rect, window_found
    try:
        windows = gw.getWindowsWithTitle(TARGET_WINDOW_TITLE)
        if windows:
            target_window = windows[0]
            
            if target_window.isMinimized:
                target_window.restore()
                time.sleep(0.1)
            
            left, top, width, height = target_window.left, target_window.top, target_window.width, target_window.height
            window_rect = (left, top, left + width, top + height)
            window_found = True
            print(f"找到目标窗口: {TARGET_WINDOW_TITLE}, 位置: {window_rect}")
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
    """截取目标窗口内容"""
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

def load_key_images():
    """加载所有按键图片并提取特征"""
    global key_images, key_name_mapping, nn_model, last_feature_load_time
    
    current_time = time.time()
    if current_time - last_feature_load_time < FEATURE_EXTRACT_INTERVAL:
        return
    
    last_feature_load_time = current_time
    print("正在加载按键图片特征...")
    
    key_images = {}
    key_name_mapping = {}
    
    if not os.path.exists(BASE_DIR):
        print(f"警告：目录 {BASE_DIR} 不存在！")
        return
    
    for key_dir in os.listdir(BASE_DIR):
        dir_path = os.path.join(BASE_DIR, key_dir)
        if not os.path.isdir(dir_path):
            continue
            
        images = []
        valid_images = 0
        for img_file in os.listdir(dir_path):
            if img_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                img_path = os.path.join(dir_path, img_file)
                try:
                    pil_img = Image.open(img_path)
                    img = np.array(pil_img.convert('L'))
                    
                    img = cv2.resize(img, (64, 64))
                    img = img.astype(np.float32) / 255.0
                    images.append(img)
                    valid_images += 1
                except Exception as e:
                    print(f"加载图片 {img_path} 出错: {e}")
        
        if valid_images > 0:
            avg_img = np.mean(images, axis=0)
            key_images[key_dir] = avg_img
            
            # 特殊处理方向键
            if key_dir in DIRECTION_KEY_MAPPING:
                key_name_mapping[key_dir] = DIRECTION_KEY_MAPPING[key_dir]
            elif key_dir == 'SPACE':
                key_name_mapping[key_dir] = 'space'
            elif key_dir == 'ENTER':
                key_name_mapping[key_dir] = 'enter'
            elif key_dir == 'CTRL':
                key_name_mapping[key_dir] = 'ctrl'
            elif key_dir == 'ALT':
                key_name_mapping[key_dir] = 'alt'
            elif key_dir == 'SHIFT':
                key_name_mapping[key_dir] = 'shift'
            elif len(key_dir) == 1 and key_dir.isalpha():
                key_name_mapping[key_dir] = key_dir.lower()
            else:
                key_name_mapping[key_dir] = key_dir.lower()
        else:
            print(f"警告：目录 {key_dir} 中没有有效图片")
    
    if key_images:
        features = []
        keys = []
        for key, img in key_images.items():
            features.append(img.flatten())
            keys.append(key)
        
        features = np.array(features)
        nn_model = NearestNeighbors(n_neighbors=min(5, len(keys)), 
                                    metric='cosine', 
                                    algorithm='auto')
        nn_model.fit(features)
        print(f"已加载 {len(key_images)} 个按键的特征，最近邻模型已训练")
    else:
        print("未找到任何按键图片！")

def extract_features(img):
    """从截图中提取特征"""
    img = cv2.resize(img, (64, 64))
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    else:
        gray = img
    return gray.astype(np.float32) / 255.0

def find_matching_keys(screenshot):
    if not key_images or nn_model is None:
        return []
    
    features = extract_features(screenshot)
    flat_features = features.flatten().reshape(1, -1)
    
    distances, indices = nn_model.kneighbors(flat_features, return_distance=True)
    
    similarities = 1 - distances[0]
    
    matched_keys = []
    for i, sim in enumerate(similarities):
        if sim > SIMILARITY_THRESHOLD:
            key = list(key_images.keys())[indices[0][i]]
            matched_keys.append((key, sim))
    
    matched_keys.sort(key=lambda x: x[1], reverse=True)
    return matched_keys[:MAX_KEYS_TO_PRESS]

def simulate_keys(matched_keys):
    if not matched_keys:
        # 没有匹配到按键时释放所有按键
        with lock:
            if currently_pressed:
                print("未匹配到任何按键，释放所有按键")
                for key in list(currently_pressed):
                    try:
                        actual_key = key_name_mapping.get(key, key)
                        keyboard.release(actual_key)
                        print(f"释放按键: {key}")
                        currently_pressed.remove(key)
                    except Exception as e:
                        print(f"释放按键 {key} 出错: {e}")
        return
    
    with lock:
        keys_to_press = [key for key, sim in matched_keys]
        
        # 释放不再需要按下的按键
        to_release = currently_pressed - set(keys_to_press)
        for key in to_release:
            try:
                actual_key = key_name_mapping.get(key, key)
                keyboard.release(actual_key)
                print(f"释放按键: {key}")
                currently_pressed.remove(key)
            except Exception as e:
                print(f"释放按键 {key} 出错: {e}")
        
        # 按下新按键
        to_press = set(keys_to_press) - currently_pressed
        for key in to_press:
            try:
                actual_key = key_name_mapping.get(key, key)
                keyboard.press(actual_key)
                key_sim = next((sim for k, sim in matched_keys if k == key), 0)
                print(f"按下按键: {key} (实际按键: {actual_key}, 相似度: {key_sim:.2f})")
                currently_pressed.add(key)
            except Exception as e:
                print(f"按下按键 {key} 出错: {e}")

def screenshot_worker():
    global window_found
    
    last_window_check = time.time()
    
    while True:
        try:
            current_time = time.time()
            if current_time - last_window_check > 5.0:
                if not find_target_window():
                    time.sleep(1)
                    continue
                last_window_check = current_time
            
            screenshot_img = capture_window()
            if screenshot_img is None:
                time.sleep(1)
                continue
            
            screenshot = np.array(screenshot_img)
            
            if screenshot.size == 0:
                print("无效截图，跳过处理")
                time.sleep(0.1)
                continue
            
            task_queue.put(("process", screenshot))
            
            time.sleep(SCREENSHOT_INTERVAL)
        except Exception as e:
            print(f"截图线程出错: {e}")
            time.sleep(1)

def processing_worker():
    while True:
        try:
            task_type, data = task_queue.get()
            
            if task_type == "load_features":
                load_key_images()
            elif task_type == "process" and data is not None:
                matched_keys = find_matching_keys(data)
                simulate_keys(matched_keys)
            
            task_queue.task_done()
        except Exception as e:
            print(f"处理线程出错: {e}")

def main():
    if not find_target_window():
        print("启动时未找到目标窗口，将继续尝试...")
    
    load_key_images()
    
    threading.Thread(target=screenshot_worker, daemon=True).start()
    threading.Thread(target=processing_worker, daemon=True).start()
    
    print(f"按键模拟程序已启动 (目标窗口: '{TARGET_WINDOW_TITLE}')")
    print(f"匹配阈值: {SIMILARITY_THRESHOLD}")
    print("按 Ctrl+C 退出程序")
    
    try:
        while True:
            time.sleep(30)
            task_queue.put(("load_features", None))
    except KeyboardInterrupt:
        print("\n正在停止程序...")

if __name__ == "__main__":
    main()
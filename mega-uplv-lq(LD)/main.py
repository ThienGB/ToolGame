import json
import time
import os
import pyautogui
import shutil
import subprocess
import ctypes
from ctypes import wintypes
from datetime import datetime
import numpy as np
import cv2
from PIL import Image
import io
import random
import string

# Try to enable DPI awareness for correct coordinate mapping on High-DPI screens
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1) # PROCESS_SYSTEM_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Enable PyAutoGUI safety feature
# NOTE: Using PostMessage (hidden clicks) will NOT be affected by FailSafe 
# because it doesn't move the system mouse.
pyautogui.FAILSAFE = True

# Windows API constants
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
GA_ROOT = 2

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def click_at(x, y):
    """
    Performs a click at (x, y) coordinates without moving the system mouse cursor.
    Uses Windows PostMessage API for 'hidden' interaction.
    """
    try:
        ix, iy = int(x), int(y)
        
        # 1. Find the window handle at the target coordinate
        hwnd_target = ctypes.windll.user32.WindowFromPoint(wintypes.POINT(ix, iy))
        if not hwnd_target:
            log(f"[Error] No window found at ({ix}, {iy})")
            return False
            
        # 2. Find the Root window. Many apps (especially games) only listen for 
        # events on their main window handle.
        hwnd_root = ctypes.windll.user32.GetAncestor(hwnd_target, GA_ROOT)
        target_hwnd = hwnd_root if hwnd_root else hwnd_target

        # Log target for debugging
        length = ctypes.windll.user32.GetWindowTextLengthW(target_hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(target_hwnd, buff, length + 1)
        window_title = buff.value or "Unknown"
        
        log(f"Independent Click -> Target: '{window_title}' at Screen({ix}, {iy})")
        
        # 3. Convert screen coordinates to window-relative coordinates
        point = wintypes.POINT(ix, iy)
        ctypes.windll.user32.ScreenToClient(target_hwnd, ctypes.byref(point))
        
        # 4. Pack relative coordinates into LPARAM
        lparam = (point.y << 16) | (point.x & 0xFFFF)
        
        # 5. Send messages
        # Some apps need WM_MOUSEMOVE before the click to register the 'hover' state
        ctypes.windll.user32.PostMessageW(target_hwnd, 0x0200, 0, lparam) # WM_MOUSEMOVE
        time.sleep(0.01)
        ctypes.windll.user32.PostMessageW(target_hwnd, 0x0201, MK_LBUTTON, lparam) # WM_LBUTTONDOWN
        time.sleep(0.1) # Longer delay for better compatibility
        ctypes.windll.user32.PostMessageW(target_hwnd, 0x0202, 0, lparam) # WM_LBUTTONUP
        
        return True
    except Exception as e:
        log(f"[Error] Background click failed: {e}")
        return False

def get_adb_screenshot(adb_path):
    """Chụp ảnh màn hình giả lập thông qua ADB và trả về dạng OpenCV image."""
    try:
        cmd = [adb_path, "shell", "screencap", "-p"]
        process = subprocess.run(cmd, capture_output=True)
        if process.returncode != 0:
            return None
        
        # Chuyển đổi dữ liệu binary sang OpenCV Image
        image_bytes = process.stdout.replace(b"\r\n", b"\n") # Sửa lỗi xuống dòng của Windows ADB
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        log(f"[Error] Failed to capture ADB screenshot: {e}")
    return None

def execute_click_image(step):
    # Thu thập tất cả các target (target, target1, target2, ...)
    targets = []
    if step.get("target"): targets.append(step.get("target"))
    
    # Tìm các target có đánh số (target1, target2, ...)
    i = 1
    while f"target{i}" in step:
        targets.append(step.get(f"target{i}"))
        i += 1
        
    timeout = step.get("timeout", 10)
    confidence = step.get("confidence", 0.8)
    
    if not targets:
        log("[Error] No targets specified for click_image")
        return False

    # Tìm đường dẫn ADB
    adb_paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
    adb_to_use = "adb"
    for path in adb_paths:
        try:
            subprocess.run([path, "version"], capture_output=True, check=True)
            adb_to_use = path
            break
        except: continue

    log(f"Starting step: click_image (Targets: {targets})")
    
    # Chuẩn bị ảnh các mục tiêu
    target_imgs = []
    for t_path in targets:
        if os.path.exists(t_path):
            t_img = cv2.imread(t_path)
            if t_img is not None:
                target_imgs.append((t_path, t_img))
        else:
            log(f"[Warning] Target image not found: {t_path}")

    if not target_imgs:
        log("[Error] No valid target images could be loaded")
        return False

    start_time = time.time()
    while time.time() - start_time < timeout:
        screen_img = get_adb_screenshot(adb_to_use)
        
        if screen_img is not None:
            # Lưu ảnh debug
            cv2.imwrite("debug_look.png", screen_img)
            
            # Quét lần lượt từng target theo thứ tự ưu tiên
            for t_path, t_img in target_imgs:
                th, tw = t_img.shape[:2]
                result = cv2.matchTemplate(screen_img, t_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                
                if max_val >= confidence:
                    click_x = max_loc[0] + tw // 2
                    click_y = max_loc[1] + th // 2
                    log(f"Success: Found '{t_path}' at ({click_x}, {click_y}) with confidence {max_val:.2f}")
                    
                    cmd = [adb_to_use, "shell", "input", "tap", str(click_x), str(click_y)]
                    subprocess.run(cmd)
                    return True
            
        time.sleep(0.5)
        
    log(f"Timeout/Failure: Could not find any of the targets {targets} within {timeout}s")
    return False

def execute_wait(step):
    duration = step.get("duration", 1)
    log(f"Starting step: wait for {duration} seconds")
    time.sleep(duration)
    log(f"Wait complete")
    return True

def execute_click_fixed(step):
    x = step.get("x")
    y = step.get("y")
    if x is None or y is None:
        log("[Error] Missing x or y coordinates for click_fixed")
        return False
        
    log(f"Starting step: click_fixed ({x}, {y})")
    # Use our new background click instead of pyautogui.click(x, y)
    if click_at(x, y):
        log(f"Success: Clicked at ({x}, {y}) (Independent)")
        return True
    else:
        log(f"Failure: Could not click at ({x}, {y})")
        return False

def execute_clear_data(step):
    path = step.get("path")
    if not path:
        log("[Error] Missing path for clear_data")
        return False
        
    log(f"Starting step: clear_data at '{path}'")
    try:
        if os.path.exists(path):
            if os.path.isdir(path):
                # Using rmtree to delete directory and its contents
                shutil.rmtree(path)
            else:
                os.remove(path)
            log(f"Success: Cleared data at '{path}'")
        else:
            log(f"Info: Path '{path}' doesn't exist, skipping clear.")
        return True
    except Exception as e:
        log(f"[Error] Could not clear data: {e}. (Ensure the game is closed)")
        return False

def execute_clear_android_data(step):
    package = step.get("package")
    if not package:
        log("[Error] Missing 'package' name for clear_android_data")
        return False
        
    log(f"Starting step: clear_android_data (ADB) for '{package}'")
    
    # Try multiple adb paths to be robust
    adb_paths = [
        "adb", # Default in system PATH
        r"C:\LDPlayer\LDPlayer9\adb.exe", # Common LDPlayer 9 path
        r"C:\LDPlayer\LDPlayer4\adb.exe"  # Common LDPlayer 4 path
    ]
    
    adb_to_use = "adb" # Default
    for path in adb_paths:
        try:
            # Test if this adb path works
            temp_cmd = [path, "version"]
            subprocess.run(temp_cmd, capture_output=True, check=True)
            adb_to_use = path
            break
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue

    try:
        # Command: adb shell pm clear <package_name>
        cmd = [adb_to_use, "shell", "pm", "clear", package]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            log(f"Success: Cleared Android data for '{package}'")
            return True
        else:
            log(f"[Error] ADB failed: {result.stderr.strip()}")
            if "device not found" in result.stderr:
                log("PLEASE ENSURE: LDPlayer is running and 'ADB Debugging/Gỡ lỗi ADB' is enabled in its settings.")
            return False
    except FileNotFoundError:
        log(f"[Error] 'adb' command not found at any of these locations: {adb_paths}")
        log("Please copy 'adb.exe' into the script folder or ensure LDPlayer is installed in the default location.")
        return False
    except Exception as e:
        log(f"[Error] Unexpected error during ADB command: {e}")
        return False

def execute_input_name(step):
    log("Starting step: input_name (Generating and typing random name)")
    
    # Tìm đường dẫn ADB
    adb_paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
    adb_to_use = "adb"
    for path in adb_paths:
        try:
            subprocess.run([path, "version"], capture_output=True, check=True)
            adb_to_use = path
            break
        except: continue

    try:
        # 1. Xóa ký tự cũ (Gửi 50 lần phím Backspace cho chắc chắn)
        log("Clearing existing text...")
        for _ in range(20):
            # 67 là KEYCODE_DEL (phím Backspace/Xóa)
            subprocess.run([adb_to_use, "shell", "input", "keyevent", "67"])
        
        # 2. Tạo tên ngẫu nhiên (7 ký tự chữ/số + 3 ký tự đặc biệt)
        chars = string.ascii_letters + string.digits
        specials = "!@#%&*+-" # Không dùng các ký tự shell có thể gây lỗi nếy không escape
        
        part1 = ''.join(random.choice(chars) for _ in range(7))
        part2 = ''.join(random.choice(specials) for _ in range(3))
        random_name = part1 + part2
        
        log(f"Generated and typing name: {random_name}")
        
        # 3. Nhập tên
        # Dùng dấu ngoặc kép để ADB shell xử lý chuỗi đúng cách
        cmd = [adb_to_use, "shell", "input", "text", f"'{random_name}'"]
        subprocess.run(cmd)
        
        log(f"Success: Typed name to field")
        return True
    except Exception as e:
        log(f"[Error] Failed to input name: {e}")
        return False

def execute_input_text(step):
    content = step.get("content", "")
    log(f"Starting step: input_text (Typing content: '{content}')")
    
    # Tìm đường dẫn ADB
    adb_paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
    adb_to_use = "adb"
    for path in adb_paths:
        try:
            subprocess.run([path, "version"], capture_output=True, check=True)
            adb_to_use = path
            break
        except: continue

    try:
        # 1. Xóa ký tự cũ
        log("Clearing existing text...")
        for _ in range(20):
            subprocess.run([adb_to_use, "shell", "input", "keyevent", "67"])
        
        # 2. Nhập nội dung
        # Dùng dấu ngoặc kép để tránh lỗi ký tự đặc biệt
        cmd = [adb_to_use, "shell", "input", "text", f"'{content}'"]
        subprocess.run(cmd)
        
        log(f"Success: Typed content '{content}'")
        return True
    except Exception as e:
        log(f"[Error] Failed to input text: {e}")
        return False

def execute_search(step):
    target_path = step.get("target")
    timeout = step.get("timeout", 5)
    confidence = step.get("confidence", 0.8)
    
    if not os.path.exists(target_path):
        log(f"[Error] Image file not found: {target_path}")
        return False

    adb_paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
    adb_to_use = "adb"
    for path in adb_paths:
        try:
            subprocess.run([path, "version"], capture_output=True, check=True)
            adb_to_use = path
            break
        except: continue

    log(f"Starting step: search '{target_path}' (Waiting for existence)")
    
    target_img = cv2.imread(target_path)
    if target_img is None: return False

    start_time = time.time()
    while time.time() - start_time < timeout:
        screen_img = get_adb_screenshot(adb_to_use)
        if screen_img is not None:
            result = cv2.matchTemplate(screen_img, target_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= confidence:
                log(f"Search Success: Found '{target_path}' (Confidence: {max_val:.2f})")
                return True
        time.sleep(0.5)
        
    log(f"Search: '{target_path}' NOT found within {timeout}s")
    return False

def main():
    script_file = "script.json"
    
    if not os.path.exists(script_file):
        log(f"[Error] {script_file} not found. Please create it first.")
        return

    try:
        with open(script_file, "r") as f:
            script = json.load(f)
    except Exception as e:
        log(f"[Error] Failed to load {script_file}: {e}")
        return

    log("Autoclick script execution started (Background Mode)...")
    
    while True: # Vòng lặp vô tận để có thể loop lại từ bước 1
        log("--- Starting new cycle from Step 1 ---")
        restart_cycle = False
        
        for index, step in enumerate(script):
            action = step.get("action")
            log(f"Step {index + 1}: {action}")
            
            result = True # Mặc định là thành công
            if action == "click_image":
                result = execute_click_image(step)
            elif action == "wait":
                result = execute_wait(step)
            elif action == "click_fixed":
                result = execute_click_fixed(step)
            elif action == "clear_data":
                result = execute_clear_data(step)
            elif action == "clear_android_data":
                result = execute_clear_android_data(step)
            elif action == "input_name":
                result = execute_input_name(step)
            elif action == "input_text":
                result = execute_input_text(step)
            elif action == "search":
                # Tìm kiếm ảnh mục tiêu
                found = execute_search(step)
                if found:
                    log("Target found. Continuing to next step...")
                    result = True
                else:
                    log("Target NOT found. Restarting from Step 1...")
                    restart_cycle = True
                    break
            else:
                log(f"Unknown action: {action}")
            
            # Nếu một bước click/nhập liệu thất bại (timeout), có thể dừng hoặc restart
            if not result and not restart_cycle:
                log(f"Step {index + 1} failed. Restarting cycle...")
                restart_cycle = True
                break
        
        if restart_cycle:
            time.sleep(2) # Đợi một chút trước khi thử lại vòng mới
            continue
            
        log("Cycle finished successfully. Restarting in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    main()


#pyinstaller --noconfirm MegaUpLvTool.spec
#pyinstaller --noconfirm MegaUpLvTool_BoxPhone.spec

# -*- coding: utf-8 -*-

import json
import time
import os
import subprocess
import threading
import random
import string
import re
import shlex
import base64
import hashlib
import uuid
import winreg
from datetime import datetime
import cv2
import numpy as np
import customtkinter as ctk
from PIL import Image
import sys
import gc

# Ensure console output uses UTF-8 to avoid UnicodeEncodeError on Windows console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# --- Fix WinError 1114 & SSL for torch/easyocr ---
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except: pass

if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    _internal = os.path.join(_meipass, '_internal')
    # Add paths for DLL search
    for dp in [_meipass, _internal, os.path.join(_internal, 'torch', 'lib'), os.path.join(_meipass, 'torch', 'lib')]:
        if os.path.exists(dp):
            if hasattr(os, 'add_dll_directory'):
                try: os.add_dll_directory(dp)
                except: pass
            os.environ['PATH'] = dp + os.pathsep + os.environ.get('PATH', '')
    
    # Force load OpenMP to avoid 1114 conflict
    try:
        import ctypes
        for dll_name in ['libiomp5md.dll', 'libiomp5.dll']:
            for base in [_meipass, _internal]:
                dp = os.path.join(base, 'torch', 'lib', dll_name)
                if os.path.exists(dp):
                    try: 
                        ctypes.CDLL(dp)
                        break
                    except: pass
    except: pass

import tkinter.filedialog as fd

# --- Biến toàn cục để nạp OCR khi cần (Lazy Load) ---
easyocr = None
_ocr_reader = None
SECRET_KEY = "RyoUTE_MegaUpLvLQ_2026"
LICENSE_FILE = "license.bin"

def init_ocr_reader(log_func=None):
    """Hàm khởi tạo OCR khi thực sự cần dùng để tránh lỗi lúc mở app"""
    global easyocr, _ocr_reader
    if _ocr_reader is not None:
        return _ocr_reader
    
    try:
        if log_func: log_func("Đang nạp bộ xử lý OCR (lần đầu sẽ mất vài giây)...")
        import easyocr as ocr_lib
        try:
            import torch
            torch.set_num_threads(1) # Giới hạn 1 luồng để không ăn hết CPU làm đơ máy
        except: pass
        
        easyocr = ocr_lib
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        _ocr_reader = _reader
        if log_func: log_func("Nạp OCR thành công.")
        return _ocr_reader
    except Exception as e:
        if log_func: log_func(f"LỖI KHÔNG NẠP ĐƯỢC OCR: {str(e)}")
        print(f"OCR Error: {e}")
        return None


# Hàm hỗ trợ tìm đường dẫn file khi đóng gói .exe
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Theme Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

NAV_COLOR = "#0F0F0F"
BG_COLOR = "#121212"
CARD_COLOR = "#1D1D1D"
ACCENT_GREEN = "#00D2FF"
ACCENT_PURPLE = "#A855F7"
ACCENT_RED = "#EF4444"

FILE_LOCK = threading.Lock()

# --- Logic Backend (AutoClicker - Hỗ trợ Single Instance) ---

class AutoClickerInstance:
    def __init__(self, device_id,  adb_path, log_func, update_ui_func, report_stats_func):
        self.device_id = device_id
        
        self.adb_path = adb_path
        self.log_func = log_func
        self.update_ui_func = update_ui_func
        self.report_stats_func = report_stats_func
        self.running = False
        self.status = "Đang chờ" # Đang chờ, Đang chạy, Lag, Xong
        self.last_step_time = time.time()
        self.is_lagging = False
        self.script = []
        self.current_account = None
        self.modes = {"login": True, "tutorial": True, "uplevel": True} # Default
        
        self.accounts_processed = 0 # Bộ đếm số acc đã chạy
        self.restart_threshold = 1 # Sau N lượt chạy sẽ khởi động lại LDPlayer 1 lần
        self.ld_console_path = None # Sẽ được gán từ App

    def log(self, msg):
        self.log_func(f"[{self.device_id}] {msg}")

    def update_status(self, status, is_lagging=False):
        self.status = status
        self.is_lagging = is_lagging
        self.update_ui_func()

    def input_text_robust(self, text):
        """Nhập text qua ADB, hỗ trợ mọi ký tự đặc biệt.
        
        Giải thích kỹ thuật:
        - ADB shell chạy lệnh qua /bin/sh -c trên thiết bị, nên ký tự |&<>()[] đếu bị interpret.
        - shlex.quote() tạo chuỗi single-quoted an toàn: 'abc|&<>' → Android shell giữ nguyên.
        - Gửi qua một arg duy nhất sau 'shell' để ADB không join/split lại args.
        """
        if not text: return
        # Tách theo space vì space phải dùng %s trong adb input text
        parts = text.split(' ')
        for i, part in enumerate(parts):
            if part:
                # shlex.quote tạo: 'kí tự đặc biệt' → Android shell không interpret
                # Ví dụ: "KI&&|<[}=GZ3" → "'KI&&|<[}=GZ3'"
                quoted = shlex.quote(part)
                cmd = [self.adb_path, "-s", self.device_id, "shell", f"input text {quoted}"]
                subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if i < len(parts) - 1:  # Có space phía sau
                self.call_adb(["shell", "input", "text", "%s"])

    def escape_adb_text(self, text):
        if not text: return ""
        # Ký tự an toàn không cần escape
        safe_chars = string.ascii_letters + string.digits
        escaped_text = ""
        for char in text:
            if char == ' ':
                escaped_text += "%s"
            elif char not in safe_chars:
                escaped_text += f"\\{char}"
            else:
                escaped_text += char
        return escaped_text

    def call_adb(self, args):
        cmd = [self.adb_path, "-s", self.device_id] + args
        # Thêm CREATE_NO_WINDOW để không bị hiện CMD khi chạy trên Win
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self):
        try:
            # Khôi phục lại lệnh shell truyền thống mà bạn đã dùng ổn định trước đó
            cmd = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
            process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if process.returncode != 0: return None
            # Xử lý ký tự xuống dòng Windows cho dữ liệu ảnh sạch
            image_bytes = process.stdout.replace(b"\r\n", b"\n")
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        except: return None

    def restart_emulator(self):
        if not self.ld_console_path or not os.path.exists(self.ld_console_path):
            self.log("CẢNH BÁO: Không tìm thấy ldconsole.exe để khởi động lại.")
            return False

        index = -1
        # Cách 1: Tìm Index bằng list2 (Chính xác cao nhất)
        try:
            res = subprocess.run([self.ld_console_path, "list2"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in res.stdout.splitlines():
                parts = line.split(',')
                if len(parts) >= 7:
                    idx_val, _, _, _, _, _, serial = parts[:7]
                    # So khớp thông minh: lấy số port ở cuối để so sánh
                    s_port = serial.split('-')[-1].split(':')[-1]
                    d_port = self.device_id.split('-')[-1].split(':')[-1]
                    
                    if (s_port == d_port and s_port.isdigit()) or (serial == self.device_id):
                        index = int(idx_val)
                        break
        except: pass

        # Cách 2: Phân tích port (Dự phòng cho máy ảo vừa mở chưa kịp hiện serial)
        if index == -1:
            port = None
            if ":" in self.device_id: port = self.device_id.split(":")[-1]
            elif "-" in self.device_id: port = self.device_id.split("-")[-1]
            if port and port.isdigit():
                index = (int(port) - 5554) // 2

        if index == -1:
            self.log("LỖI: Không xác định được index máy ảo để restart.")
            return False

        self.log(f"==> ĐANG KHỞI ĐỘNG LẠI MÁY ẢO (Index {index})...")
        self.update_status(f"Restarting LD {index}")
        
        # 1. Tắt máy ảo
        subprocess.run([self.ld_console_path, "quit", "--index", str(index)], creationflags=subprocess.CREATE_NO_WINDOW)
        
        # Đợi tắt hẳn (tránh lỗi launch khi instance đang closing)
        start_quit = time.time()
        while time.time() - start_quit < 30:
            if not self.running: return False
            time.sleep(2)
            try:
                res = subprocess.run([self.ld_console_path, "list2"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                is_running = False
                for line in res.stdout.splitlines():
                    parts = line.split(',')
                    if len(parts) >= 5 and parts[0] == str(index):
                        if parts[4] != '0': is_running = True
                        break
                if not is_running: break
            except: break

        time.sleep(3)
        
        # 2. Bật lại máy ảo
        subprocess.run([self.ld_console_path, "launch", "--index", str(index)], creationflags=subprocess.CREATE_NO_WINDOW)
        
        # 3. Chờ máy ảo lên và sẵn sàng
        self.log(f"Đang đợi máy ảo (Index {index}) ổn định ADB (Tối đa 70s)...")
        start_wait = time.time()
        
        guest_port = 5554 + (index * 2)
        guest_serial = f"127.0.0.1:{guest_port}"

        while time.time() - start_wait < 70: # Rút ngắn xuống còn khoảng 1 phút như yêu cầu
            if not self.running: return False
            
            # Thử connect liên tục vào port tiêu chuẩn
            subprocess.run([self.adb_path, "connect", guest_serial], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)

            # Cập nhật serial thực tế từ list2 (Nguồn tin cậy nhất để quét lại device)
            current_ld_serial = None
            try:
                res = subprocess.run([self.ld_console_path, "list2"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in res.stdout.splitlines():
                    parts = line.split(',')
                    if len(parts) >= 7 and parts[0] == str(index):
                        for p in parts:
                            p = p.strip()
                            if (":" in p or p.startswith("emulator-")) and p != "null" and "." in p:
                                current_ld_serial = p
                                break
                        break
            except: pass

            # Nếu list2 báo có serial mới, thử connect và cập nhật ngay
            if current_ld_serial:
                subprocess.run([self.adb_path, "connect", current_ld_serial], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                if current_ld_serial != self.device_id:
                    self.log(f"Quét lại phát hiện Serial mới: {current_ld_serial}")
                    self.device_id = current_ld_serial
            
            # Kiểm tra xem device_id hiện tại đã online chưa
            res_adb = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            is_connected = False
            for line in res_adb.stdout.splitlines():
                if self.device_id in line and "device" in line and "offline" not in line and "unauthorized" not in line:
                    is_connected = True
                    break
            
            if is_connected:
                # Kiểm tra phản hồi shell thực tế (getprop hoặc wm size)
                res_boot = self.call_adb(["shell", "getprop", "sys.boot_completed"])
                if b"1" in res_boot.stdout:
                    self.log("==> KẾT NỐI THÀNH CÔNG! Thiết bị đã sẵn sàng.")
                    time.sleep(5) # Giảm thời gian chờ sau khi lên hẳn
                    return True
                
                # Dự phòng nếu boot_completed bị treo lâu nhưng shell đã chạy
                if time.time() - start_wait > 45:
                    res_wm = self.call_adb(["shell", "wm", "size"])
                    if b"Physical size" in res_wm.stdout:
                        self.log("==> KẾT NỐI THÀNH CÔNG (qua wm size)!")
                        time.sleep(5)
                        return True

            time.sleep(3) # Tần suất quét lại dầy hơn (mỗi 3s)
        
        return False
    def click_coords_logic(self, step):
        x, y = step.get("x"), step.get("y")
        if x is not None and y is not None:
            delay = step.get("timeout", 0)
            if delay > 0: time.sleep(delay)
            self.call_adb(["shell", "input", "tap", str(x), str(y)])
            self.log(f"CLICK TỌA ĐỘ: ({x}, {y})")
            return True
        return False

    def execute_step(self, step):
        if not self.running: return False
        action = step.get("action")
        target_info = step.get("target") or step.get("target1", "")
        self.log(f"==> Bước: {action} {f'({target_info})' if target_info else ''}")
        self.last_step_time = time.time()
        res = True
        if action == "click_image":
            res = self.click_image_logic(step)
        elif action == "click_image_if":
            if self.click_image_logic(step):
                # Nếu tìm thấy và click được ảnh chính, thực hiện thêm các bước phụ nếu có
                for sub_step in step.get("then", []):
                    if not self.execute_step(sub_step):
                        break
            res = True
        elif action == "wait":
            wait_time = step.get("duration") or step.get("timeout") or 1
            time.sleep(wait_time)
            res = True
        elif action == "clear_android_data":
            pkg = step.get("package")
            self.call_adb(["shell", "pm", "clear", pkg])
            res = True
        elif action == "input_name":
            res = self.input_name_logic()
        elif action == "input_text":
            res = self.input_text_logic(step)
        elif action == "input_account":
            res = self.input_account_logic()
        elif action == "input_password":
            res = self.input_password_logic()
        elif action == "search":
            res = self.search_logic(step)
        elif action == "get_room_id":
            res = self.get_room_id_logic(step)
        elif action == "wait_for_players":
            res = self.wait_for_players_logic(step)
        elif action == "wait_for_room":
            res = self.wait_for_room_logic(step)
        elif action == "input_room_id":
            res = self.input_room_id_logic()
        elif action == "click_coords":
            res = self.click_coords_logic(step)
        elif action == "click_any":
            res = self.click_any_logic(step)
        elif action == "swipe":
            res = self.swipe_logic(step)
        elif action == "press_esc":
            res = self.press_esc_logic(step)
        elif action == "cases":
            res = self.cases_logic(step)
        elif action == "sync_autowin":
            res = self.sync_autowin_logic(step)
        elif action == "loop":
            # Lặp lại một nhóm hành động N lần
            count = step.get("count", 1)
            sub_steps = step.get("steps", [])
            for i in range(count):
                if not self.running: return False
                self.log(f"--- Bắt đầu lặp lượt {i+1}/{count} ---")
                for s in sub_steps:
                    if not self.execute_step(s):
                        return False
            res = True
        
        # Kiểm tra lag: Nếu 1 bước mất hơn 35s
        duration = time.time() - self.last_step_time
        if duration > 35: 
             self.update_status("Lag", True)
        else:
             self.update_status("Đang chạy", False)

        return res

    def click_image_logic(self, step):
        targets = []
        if step.get("target"): targets.append(step.get("target"))
        i = 1
        while f"target{i}" in step:
            targets.append(step.get(f"target{i}"))
            i += 1
        
        timeout = step.get("timeout", 10)
        confidence = step.get("confidence", 0.8)
        use_color = step.get("use_color", step.get("useColor", False))

        # Ưu tiên chọn hình của mỗi worker để giảm chọn trùng cùng lúc
        ordered_targets = list(targets)
        if len(targets) > 1 and hasattr(self, 'worker_index'):
            idx = self.worker_index % len(targets)
            ordered_targets = targets[idx:] + targets[:idx]
            self.log(f"[Worker {self.worker_index}] Ưu tiên chọn: {ordered_targets[0]}")

        target_imgs = []
        for t_path in ordered_targets:
            real_path = resource_path(t_path)
            if os.path.exists(real_path):
                # Đọc ảnh ở dạng màu hoặc xám tùy cài đặt
                read_mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
                img = cv2.imread(real_path, read_mode)
                if img is not None: target_imgs.append((t_path, img))
            else:
                self.log(f"LỖI: Không tìm thấy ảnh mẫu: {t_path}")

        start = time.time()
        last_log_time = 0
        while time.time() - start < timeout and self.running:
            # Log mỗi 5s để biết là vẫn đang tìm
            if time.time() - last_log_time > 5:
                self.log(f"Đang chờ ảnh (đã chờ {(time.time() - start):.1f}s/{timeout}s)...")
                last_log_time = time.time()

            screen = self.get_screenshot()
            if screen is not None:
                # Chuyển ảnh màn hình sang dạng xám nếu không dùng màu
                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                
                for t_path, t_img in target_imgs:
                    res = cv2.matchTemplate(compare_screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val >= confidence:
                        th, tw = t_img.shape[:2]
                        cx, cy = max_loc[0] + tw//2, max_loc[1] + th//2
                        # Vẫn click trên tọa độ gốc
                        self.call_adb(["shell", "input", "tap", str(cx), str(cy)])
                        self.log(f"==> CLICK THÀNH CÔNG: {os.path.basename(t_path)} (Khớp: {max_val:.2f})")
                        return True
            time.sleep(1)
        self.log(f"!! THẤT BẠI: Không tìm thấy ảnh sau {timeout}s")
        return False

    def search_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        use_color = step.get("use_color", step.get("useColor", False))
        
        real_path = resource_path(target)
        if not os.path.exists(real_path): return False
        
        read_mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
        t_img = cv2.imread(real_path, read_mode)
        if t_img is None: return False
        
        start = time.time()
        last_log_time = 0
        while time.time() - start < timeout and self.running:
            if time.time() - last_log_time > 5:
                self.log(f"Đang tìm kiếm (đã chờ {(time.time() - start):.1f}s/{timeout}s)...")
                last_log_time = time.time()
                
            screen = self.get_screenshot()
            if screen is not None:
                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                res = cv2.matchTemplate(compare_screen, t_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= conf:
                    self.log(f"==> TÌM THẤY: {os.path.basename(target)} (Khớp: {max_val:.2f})")
                    return True
            time.sleep(1)
        self.log(f"!! KHÔNG TÌM THẤY: {os.path.basename(target)} sau {timeout}s")
        return False

    def cases_logic(self, step):
        cases = step.get("cases", [])
        if not cases: return True
        
        timeout = step.get("timeout", 10)
        confidence = step.get("confidence", 0.8)
        
        start_time = time.time()
        while time.time() - start_time < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(1)
                continue
            
            for case in cases:
                triggers = []
                if case.get("trigger"): triggers.append(case.get("trigger"))
                idx = 1
                while f"trigger{idx}" in case:
                    triggers.append(case.get(f"trigger{idx}"))
                    idx += 1
                
                case_conf = case.get("confidence", confidence)
                sub_script = case.get("script", [])
                
                for t_path in triggers:
                    real_path = resource_path(t_path)
                    if not os.path.exists(real_path): continue
                    t_img = cv2.imread(real_path, cv2.IMREAD_GRAYSCALE)
                    if t_img is None: continue
                    
                    scr_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    res = cv2.matchTemplate(scr_gray, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    if mv >= case_conf:
                        self.log(f"-> PHÁT HIỆN: {os.path.basename(t_path)} ({mv:.2f})")
                        for s_step in sub_script:
                            if not self.running: break
                            self.execute_step(s_step)
                        return True
            time.sleep(1)
        return False

    def click_any_logic(self, step):
        wait_time = step.get("wait") or step.get("timeout") or 0
        if wait_time > 0:
            self.log(f"Đang đợi {wait_time}s trước khi click...")
            time.sleep(wait_time)
        
        screen = self.get_screenshot()
        if screen is not None:
            h, w = screen.shape[:2]
            cx, cy = w // 2, h // 2
            self.call_adb(["shell", "input", "tap", str(cx), str(cy)])
            self.log(f"==> CLICK ANY (Center): ({cx}, {cy})")
            return True
        
        self.log("!! LỖI: Không lấy được kích thước màn hình để click.")
        return False

    def swipe_logic(self, step):
        # Lấy kích thước màn hình
        screen = self.get_screenshot()
        if screen is not None:
            h, w = screen.shape[:2]
        else:
            # Fallback nếu không fail được (thường hiếm khi xảy ra ở bước này)
            h, w = 1080, 1920 

        def get_val(val, max_v):
            if val is None: return 0
            if isinstance(val, (float, int)) and val <= 1.0:
                return int(val * max_v)
            return int(val)

        # Mặc định từ dưới lên trên (cuộn xuống)
        x1 = get_val(step.get("x1", 0.5), w)
        y1 = get_val(step.get("y1", 0.8), h)
        x2 = get_val(step.get("x2", 0.5), w)
        y2 = get_val(step.get("y2", 0.3), h)
        duration = step.get("duration", 500)

        self.call_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
        self.log(f"==> SWIPE: ({x1}, {y1}) -> ({x2}, {y2}) trong {duration}ms")
        return True

    def press_esc_logic(self, step):
        wait_time = step.get("wait") or 0
        if wait_time > 0:
            self.log(f"Đang đợi {wait_time}s trước khi bấm ESC...")
            time.sleep(wait_time)
        
        # Sử dụng keyevent 111 cho ESCAPE. 
        # Nếu muốn dùng phím Back của Android thì đổi thành 4.
        self.call_adb(["shell", "input", "keyevent", "111"])
        self.log("==> PRESS ESC (Keyevent 111)")
        return True

    def input_name_logic(self):
        # Gửi 20 phím xóa cùng lúc thay vì gọi vòng lặp
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        name = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(7)) + ''.join(random.choice("!@#%&*+-") for _ in range(3))
        safe_name = self.escape_adb_text(name)
        self.call_adb(["shell", "input", "text", safe_name])
        return True

    def input_text_logic(self, step):
        content = step.get("content", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        self.input_text_robust(content)
        return True

    def input_account_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("tk", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
        self.input_text_robust(content)
        return True

    def input_password_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("mk", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
        self.input_text_robust(content)
        return True

    def get_room_id_logic(self, step=None):
        """
        Đọc mã phòng bằng EasyOCR (chỉ cần pip install easyocr).
        Không cần phần mềm ngoài, không cần bộ ảnh số.

        Cấu hình trong step:
          - roi:               [x, y, w, h] tỷ lệ 0.0-1.0
          - room_id_min_length: Số ký tự tối thiểu (mặc định 6)
          - room_id_max_length: Số ký tự tối đa   (mặc định 7)
          - timeout:           Giới hạn thời gian (mặc định 30s)
        """
        global _ocr_reader
        if step is None: step = {}
        
        # Khởi tạo OCR lười (chỉ gọi khi thực sự cần dùng)
        reader = init_ocr_reader(self.log)
        if reader is None:
            return False

        roi          = step.get("roi", [0.50, 0.0, 0.30, 0.10])
        room_id_min  = step.get("room_id_min_length", 6)
        room_id_max  = step.get("room_id_max_length", 7)
        timeout      = step.get("timeout", 30)

        self.log(f"OCR: Đang đọc ID phòng trong ROI {roi} ...")
        start   = time.time()
        attempt = 0

        while time.time() - start < timeout and self.running:
            attempt += 1
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(1)
                continue

            h_full, w_full = screen.shape[:2]

            # === CẮT VÙNG ROI ===
            rx, ry, rw, rh = roi
            if all(v <= 1.0 for v in roi):
                x1 = int(rx * w_full);        y1 = int(ry * h_full)
                x2 = int((rx + rw) * w_full); y2 = int((ry + rh) * h_full)
            else:
                x1, y1 = int(rx), int(ry);   x2, y2 = int(rx + rw), int(ry + rh)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w_full, x2), min(h_full, y2)

            crop = screen[y1:y2, x1:x2]

            # === TIỀN XỬ LÝ: Phóng to 2x giúp OCR nhận chữ nhỏ chính xác hơn ===
            scale = 2
            crop  = cv2.resize(crop, (crop.shape[1] * scale, crop.shape[0] * scale),
                               interpolation=cv2.INTER_CUBIC)

            # Xóa ID cũ trước khi lấy ID mới để Guest không đọc nhầm
            with self.shared_data["lock"]:
                if "room_ids" in self.shared_data and self.group_id in self.shared_data["room_ids"]:
                    del self.shared_data["room_ids"][self.group_id]
                if "joined_counts" in self.shared_data:
                    self.shared_data["joined_counts"][self.group_id] = 1 # Host tự tính là 1

            # === ĐỌC OCR ===
            # Thêm allowlist='0123456789ID: ' để chỉ nhận diện số và chữ ID, giúp ID không bị dính chùm thành 10
            results = reader.readtext(
                crop,
                detail=1,
                allowlist='0123456789ID: '
            )

            # Gộp tất cả text tìm được
            raw_text = ' '.join([r[1] for r in results])
            
            # Tìm cụm khoảng 6-7 chữ số liên tiếp
            numbers_only = re.findall(r'\d+', raw_text)
            res_id = ""
            for n in numbers_only:
                if room_id_min <= len(n) <= room_id_max:
                    res_id = n
                    break
            
            # Đề phòng OCR đọc chữ I, D thành 1, 0 (vd ID 123456 -> 10 123456)
            # res_id sẽ trúng khớp "123456" vì "10" ngoài khoảng yêu cầu (6-7 kí tự)

            self.log(f"  OCR lần {attempt}: raw='{raw_text}' -> Lọc: '{res_id}'")

            if res_id and room_id_min <= len(res_id) <= room_id_max:
                with self.shared_data["lock"]:
                    if "room_ids" not in self.shared_data:
                        self.shared_data["room_ids"] = {}
                    if "joined_counts" not in self.shared_data:
                        self.shared_data["joined_counts"] = {}
                    self.shared_data["room_ids"][self.group_id] = res_id
                    self.shared_data["joined_counts"][self.group_id] = 1  # Host tính là 1
                self.log(f"==> QUÉT ĐƯỢC ID PHÒNG: [{res_id}] ({len(res_id)} ký tự) ✓")
                return True
            elif len(res_id) > room_id_max:
                self.log(f"  Chuỗi dài hơn dự kiến. Kiểm tra lại ROI.")
            else:
                self.log(f"  Chưa đủ số. Đang chờ ID hiển thị...")

            time.sleep(2.5) # Tăng thơi gian chờ để đỡ chiếm CPU

        self.log(f"!! THẤT BẠI: Không đọc được ID phòng qua OCR sau {timeout}s")
        return False

    def wait_for_room_logic(self, step):
        timeout = step.get("timeout", 300)
        self.log("Đang chờ Host gửi mã phòng...")
        start = time.time()
        while time.time() - start < timeout and self.running:
            with self.shared_data["lock"]:
                if self.shared_data.get("room_ids", {}).get(self.group_id):
                    return True
            time.sleep(2)
        return False

    def input_room_id_logic(self):
        with self.shared_data["lock"]:
            rid = self.shared_data.get("room_ids", {}).get(self.group_id, "")
        if not rid:
            self.log("LỖI: Chưa có mã phòng để nhập.")
            return False
        
        self.log(f"Bắt đầu click nhập mã phòng: {rid}")
        
        # Tải sẵn ảnh 10 nút số (images/btn_0.png ... images/btn_9.png)
        digit_imgs = {}
        for i in range(10):
            p = resource_path(f"images/btn_{i}.png")
            if os.path.exists(p):
                img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    digit_imgs[str(i)] = img
            else:
                self.log(f"LỖI: Thiếu ảnh nút số: images/btn_{i}.png")
        
        if len(digit_imgs) < 10:
            self.log("LỖI: Thiếu bộ ảnh nút số. Cần có images/btn_0.png đến images/btn_9.png")
            return False
        
        # Click lần lượt từng chữ số trong ID
        for digit in rid:
            if not self.running: return False
            if digit not in digit_imgs:
                continue
            
            t_img = digit_imgs[digit]
            found = False
            # Thử 3 lần để chắc chắn bắt được nút
            for _ in range(3):
                screen = self.get_screenshot()
                if screen is not None:
                    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    res = cv2.matchTemplate(gray, t_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.85:
                        th, tw = t_img.shape[:2]
                        cx, cy = max_loc[0] + tw // 2, max_loc[1] + th // 2
                        self.call_adb(["shell", "input", "tap", str(cx), str(cy)])
                        self.log(f"  Click số '{digit}' tại ({cx}, {cy})")
                        found = True
                        time.sleep(0.5)  # Đợi 0.5s giữa 2 lần click để game nhận phím
                        break
                time.sleep(0.5)
            
            if not found:
                self.log(f"!! Không tìm thấy nút số '{digit}' trên màn hình!")
                return False
        
        self.log(f"==> Nhập xong mã phòng: {rid}")
        time.sleep(0.5)
        
        with self.shared_data["lock"]:
            if self.group_id not in self.shared_data["joined_counts"]:
                self.shared_data["joined_counts"][self.group_id] = 0
            self.shared_data["joined_counts"][self.group_id] += 1
        return True

    def wait_for_players_logic(self, step):
        target_count = step.get("count", 4) + 1 # +1 cho Host
        timeout = step.get("timeout", 300)
        start = time.time()
        while time.time() - start < timeout and self.running:
            with self.shared_data["lock"]:
                current = self.shared_data.get("joined_counts", {}).get(self.group_id, 0)
            if current >= target_count:
                self.log(f"ĐỦ ĐỘI ({current}/{target_count}). BẮT ĐẦU!")
                return True
            else:
                self.update_status(f"Gần đủ ({current}/{target_count})")
                time.sleep(2)
        return False

    def sync_autowin_logic(self, step):
        timeout = step.get("timeout", 120)
        start = time.time()

        with self.shared_data["lock"]:
            if "autowin_barrier" not in self.shared_data:
                self.shared_data["autowin_barrier"] = {}
            if self.group_id not in self.shared_data["autowin_barrier"]:
                self.shared_data["autowin_barrier"][self.group_id] = 0
            self.shared_data["autowin_barrier"][self.group_id] += 1
            self.log(f"Đã vào hàng chờ auto win: {self.shared_data['autowin_barrier'][self.group_id]}/5")

        while time.time() - start < timeout and self.running:
            with self.shared_data["lock"]:
                current = self.shared_data.get("autowin_barrier", {}).get(self.group_id, 0)
            if current >= 5:
                break
            time.sleep(0.5)

        if not self.running:
            return False

        with self.shared_data["lock"]:
            current = self.shared_data.get("autowin_barrier", {}).get(self.group_id, 0)
            if current < 5:
                self.log(f"!! Hết thời gian chờ auto win đồng bộ ({current}/5)")
                return False

        # Nhấn auto win đồng thời khi cả 5 tab đều cùng tới hàng chờ
        self.click_image_logic({"action": "click_image_if", "target": "images/on.png", "timeout": 20, "confidence": 0.9})

        with self.shared_data["lock"]:
            self.shared_data["autowin_barrier"][self.group_id] = 0

        return True

    def run(self, accounts, modes_func, worker_index, shared_data):
        self.accounts_list = accounts
        self.modes_func = modes_func
        self.worker_index = worker_index
        self.group_id = self.worker_index // 5
        self.shared_data = shared_data
        self.running = True
        
        # 1. GIAI ĐOẠN LOGIN
        login_script = [
            

            {"action": "click_image_if", "target": "images/game_logo.png", "timeout": 10, "confidence": 0.7},
            {"action": "click_image", "target": "images/login_garena.png", "timeout": 420, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/login_garena.png", "timeout": 30, "confidence": 0.9},

            {"action": "click_image", "target1": "images/username.png","target2": "images/account_input.png", "target3": "images/account.jpg","timeout": 60, "confidence": 0.9},
            {"action": "input_account"},
            {"action": "click_image", "target1": "images/password.png","target2": "images/input_password.png", "target3": "images/matkhau.jpg", "timeout": 60, "confidence": 0.9},
            {"action": "input_password"},
            {"action": "click_image", "target1": "images/login.png", "target2": "images/login_now.png", "target3": "images/dangnhap.jpg", "timeout": 30, "confidence": 0.9},
            {"action": "wait", "timeout": 5},
            {"action": "click_image_if", "target1": "images/login.png", "target2": "images/login_now.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_image", "target": "images/ok2.png", "timeout": 30, "confidence": 0.9},
            {"action": "wait", "timeout": 7},
            {"action": "click_image_if", "target": "images/ok2.png", "timeout": 4, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ok2.png", "timeout": 4, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/batdau.png", "timeout": 6, "confidence": 0.9},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},

        ]

        # 2. GIAI ĐOẠN VƯỢT TÂN THỦ
        tutorial_script = [
            {
                "action": "click_image_if", 
                "target": "images/vao_tran_button_1.png", 
                "timeout": 20, 
                "confidence": 0.9,
                "then": [
                    {"action": "click_image_if", "target": "images/vao_tran_button_1.png", "timeout": 3, "confidence": 0.9},
                    {"action": "click_image_if", "target": "images/vao_tran_button_1.png", "timeout": 3, "confidence": 0.9},
                    {"action": "click_image_if", "target": "images/vao_tran_button_1.png", "timeout": 3, "confidence": 0.9},
                    {"action": "click_image_if", "target": "images/vao_tran_button_1.png", "timeout": 3, "confidence": 0.9},
                    {"action": "wait", "timeout": 5},
                    {"action": "click_image", "target1": "images/vao_tran_button_2.png", "target2": "images/vao_tran_button3.png", "timeout": 30, "confidence": 0.9},
                    {"action": "click_image_if", "target1": "images/vao_tran_button_2.png", "target2": "images/vao_tran_button3.png", "timeout": 4, "confidence": 0.9}
                ]
            },
            {"action": "click_image_if", "target1": "images/skip.png","target2": "images/dkysau.jpg", "timeout": 20, "confidence": 0.9},
            {
                "action": "click_image_if", 
                "target": "images/vao_button.png", 
                "timeout": 10, 
                "confidence": 0.9,
                "then": [
                   {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.9},
                   {"action": "click_image_if", "target": "images/on.png", "timeout": 20, "confidence": 0.9,"use_color": True},
                   {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
                   {"action": "click_image_if", "target": "images/victory.png", "timeout": 200, "confidence": 0.9},
                   {"action": "click_image_if", "target": "images/victory.png", "timeout": 20, "confidence": 0.9},
                   {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.9},
                   {"action": "click_image_if", "target": "images/off.png", "timeout": 20, "confidence": 0.9,"use_color": True},
                   {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
                   {"action": "click_any", "wait": 10},
                   
                ]
            },
            {"action": "wait", "timeout": 5},
            {"action": "click_coords", "x": 48, "y": 92, "timeout": 2},
            {"action": "wait", "timeout": 2},
            {"action": "press_esc", "wait": 3} ,
            {"action": "press_esc", "wait": 3} ,
            {"action": "click_image", "target": "images/pvp.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/1v1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/x2.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_image", "target": "images/pve.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/on.png", "timeout": 20, "confidence": 0.9,"use_color": True},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/ready.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ready.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image", "target1": "images/tuong5.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/victory.png", "timeout": 120, "confidence": 0.9},
            {"action": "wait", "timeout": 20},
            {"action": "click_image_if", "target": "images/victory.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 10, "confidence": 0.9},
            {"action": "wait", "timeout": 5},
            {"action": "click_image", "target": "images/daulai.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/ready.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ready.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image", "target1": "images/tuong5.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/victory.png", "timeout": 120, "confidence": 0.9},
            {"action": "wait", "timeout": 20},
            {"action": "click_image_if", "target": "images/victory.png", "timeout": 10, "confidence": 0.9},
            {"action": "wait", "timeout": 5},
            {"action": "click_image", "target": "images/lobby.png", "timeout": 20, "confidence": 0.9},
            
            {"action": "click_image_if", "target1": "images/dau_hang_button.png", "target2": "images/dauhang.png","timeout": 7, "confidence": 0.9},
            
            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2} ,
            {"action": "click_image", "target1": "images/nhan_sktt.png", "target2": "images/nhan_sktt1.png","timeout": 60, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/nhan_sktt.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_coords", "x": 774, "y": 246, "timeout": 2},
            {"action": "click_coords", "x": 774, "y": 246, "timeout": 2},
            {"action": "click_any", "wait": 4},
            {"action": "press_esc", "wait": 2} ,
            {"action": "wait", "timeout": 5},
            {"action": "click_image_if", "target": "images/lam_event.png", "timeout": 5, "confidence": 0.9},
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "click_image", "target": "images/event_default.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/lam_event.png", "timeout": 5, "confidence": 0.9},
            {"action": "press_esc", "wait": 3} ,
            {"action": "press_esc", "wait": 3} ,
            {"action": "wait", "timeout": 5},
            {"action": "click_image_if", "target1": "images/dau_hang_button.png", "target2": "images/dauhang.png","target3": "images/dauhang1.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 3} ,
            {"action": "click_image_if", "target": "images/co.png", "timeout": 7, "confidence": 0.9},
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "click_coords", "x": 841, "y": 97, "timeout": 3},
            {"action": "press_esc", "wait": 3} ,
            {"action": "click_coords", "x": 26, "y": 228, "timeout": 3},
            {"action": "click_coords", "x": 26, "y": 228, "timeout": 3},
            {"action": "wait", "timeout": 3},
            {"action": "swipe", "x1": 0.2, "y1": 0.8, "x2": 0.2, "y2": 0.2, "duration": 600},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target1": "images/sktt.jpg", "target2": "images/sktt1.jpg", "target3": "images/sktt2.jpg", "target4": "images/sktt3.jpg", "target5": "images/sktt4.jpg", "target6": "images/sktt5.jpg", "target7": "images/sktt6.jpg", "target8": "images/sktt7.jpg", "target9": "images/sktt8.jpg", "target10": "images/sktt9.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target1": "images/sktt.jpg", "target2": "images/sktt1.jpg", "target3": "images/sktt2.jpg", "target4": "images/sktt3.jpg", "target5": "images/sktt4.jpg", "target6": "images/sktt5.jpg", "target7": "images/sktt6.jpg", "target8": "images/sktt7.jpg", "target9": "images/sktt8.jpg", "target10": "images/sktt9.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/nhan_ruby_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/thoat_sk.png","target2": "images/quaylaisktt.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/tui_do_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image", "target1": "images/vat_pham.png", "target2": "images/vat_pham1.png","target3": "images/vat_pham2.png","target4": "images/vat_pham3.png","target5": "images/vat_pham4.png","target6": "images/vat_pham5.png","timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target1": "images/su_dung_button.png","target2": "images/su_dung.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/ok.png","target2": "images/ok1.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2} ,
            {"action": "click_image", "target": "images/shop.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 80, "y": 256, "timeout": 2},
            {"action": "click_coords", "x": 80, "y": 256, "timeout": 2},
            {"action": "click_image", "target": "images/shopruby.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 580, "y": 512, "timeout": 2},
            {"action": "click_coords", "x": 580, "y": 512, "timeout": 2},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/200_ruby.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/buy_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/mo_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2} ,
        ]

        # 2.5 GIAI ĐOẠN MUA EXP
        mua_exp_script = [
            {"action": "click_image", "target": "images/andetieptuc.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/andetieptuc.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/andetieptuc.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            
            {"action": "click_image", "target1": "images/x3.png", "target2": "images/x_nvtl.png","timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},

            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2} ,
            {"action": "click_coords", "x": 782, "y": 20, "timeout": 2},
            {"action": "click_coords", "x": 782, "y": 20, "timeout": 2},
            {"action": "click_coords", "x": 72, "y": 153, "timeout": 2},
            {"action": "click_coords", "x": 72, "y": 153, "timeout": 2},
            {"action": "click_image", "target": "images/nhan_nhanh.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 229, "y": 490, "timeout": 2},
            {"action": "click_coords", "x": 229, "y": 490, "timeout": 2},
            {"action": "click_image", "target1": "images/ok_ruby.jpg", "target2": "images/ok_nvtl.png", "timeout": 20, "confidence": 0.9},
            {"action": "press_esc", "wait": 2} ,
            {"action": "click_image", "target": "images/shop.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 80, "y": 256, "timeout": 2},
            {"action": "click_coords", "x": 80, "y": 256, "timeout": 2},
            {"action": "click_image", "target": "images/shopruby.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 580, "y": 512, "timeout": 2},
            {"action": "click_coords", "x": 580, "y": 512, "timeout": 2},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/200_ruby.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/buy_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/mo_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_coords", "x": 429, "y": 369, "timeout": 2},
            {"action": "click_coords", "x": 429, "y": 369, "timeout": 2},
            {"action": "click_image", "target": "images/buy.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/buy_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/mo_button.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2} ,
        ]

        # 3. GIAI ĐOẠN DÍNH GAME
        dinh_game_script = [
            {"action": "click_image", "target": "images/dauthuong.png", "timeout": 60, "confidence": 0.9},
            {"action": "click_image", "target1": "images/logo.png","target2": "images/logo4.png","target3": "images/logo1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/off.png", "timeout": 20, "confidence": 0.9,"use_color": True},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/ready.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 3, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/sansang5v5.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images/ok3.png", "timeout": 15, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            
            
            
            {"action": "click_image_if", "target": "images/tuong5.png", "timeout": 10, "confidence": 0.9},
            
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 10, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/logo.png", "target2": "images/logo1.png", "target3": "images/logo2.png", "target4": "images/logo3.png", "timeout": 50, "confidence": 0.9},
            {
                "action": "loop",
                "count": 4,
                "steps": [
                    {"action": "click_image", "target": "images/ban_do.png", "timeout": 200, "confidence": 0.9},
                    {"action": "wait", "timeout": 15}
                ]
            },
            {"action": "click_image_if", "target": "images/logo.png", "target2": "images/logo1.png", "target3": "images/logo2.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/on.png", "timeout": 20, "confidence": 0.9,"use_color": True},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/victory.png", "timeout": 120, "confidence": 0.9},
            {"action": "wait", "timeout": 20},
            {"action": "click_image_if", "target": "images/victory.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_any", "wait": 3},
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "press_esc", "wait": 2} ,
           
            {"action": "press_esc", "wait": 2} ,
            {
                "action": "cases",
                "timeout" : 120,
                "cases": [
                    {
                        "trigger": "images/event_default.png",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image", "target": "images/event_default.png", "timeout": 20, "confidence": 0.9},
                            {"action": "press_esc", "wait": 2},
                            
                        ]
                    },
                    {
                        "trigger": "images/pvp.png", 
                        "confidence": 0.7,
                        
                    },
                    {
                        "trigger": "images/x5.png", 
                        "script": [
                        {"action": "click_image_if", "target": "images/x5.png", "timeout": 10, "confidence": 0.9},
                        ]
                    },
                ]
              } ,     
            
            {"action": "press_esc", "wait": 2},
            
            
            {"action": "press_esc", "wait": 2} ,
            
        ]

        # 4. GIAI ĐOẠN GHÉP ĐỘI (TEAM UP)
                  
        teamup_host_script = [
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "click_image", "target": "images/team5.png", "timeout": 60},
            {"action": "click_image_if", "target": "images/x2.png", "timeout": 7, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/x1.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/x1.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/huy.png", "timeout": 3, "confidence": 0.9},
            {
                "action": "get_room_id",
                "timeout": 30,
                # ID phòng nằm ở: 0-10% dọc, 50-80% ngang
                # roi: [x, y, width, height] theo tỷ lệ màn hình
                "roi": [0.50, 0.0, 0.30, 0.10],
                "room_id_length": 6,   # Đổi thành 7 nếu ID phòng có 7 chữ số
                "room_id_min_length": 6,  # Chấp nhận 6 hoặc 7 ký tự
                "room_id_max_length": 7,
                "confidence": 0.88,
                "min_gap": 8,
            },
            
            
            {"action": "wait_for_players", "count": 4, "timeout": 300}, # Chờ 4 người khác vào
           
            
            {"action": "click_image_if", "target": "images/da_ro.png", "timeout": 5, "confidence": 0.9},
            {"action": "click_image", "target": "images/pve.png", "timeout": 30},
            {"action": "click_image", "target": "images/ready.png", "timeout": 30},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 3, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/ready.png", "timeout": 5, "confidence": 0.9},
            
        ]
        
        teamup_guest_script = [
            {"action": "press_esc", "wait": 2} ,
            
            {"action": "click_image", "target": "images/pvp.png", "timeout": 60, "confidence": 0.9},
            {"action": "click_image", "target": "images/idphong.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait_for_room", "timeout": 300}, # Chờ Host quét xong ID
            {"action": "input_room_id"},
            {"action": "click_image", "target": "images/vao.png", "timeout": 30},
           

        ]

        # 5. CÁC HÀNH ĐỘNG LẶP LẠI SAU KHI VÀO PHÒNG (SHARED BATTLE LOGIC)
        # Thiết kế dạng list để bạn có thể gọi lại nhiều lần hoặc dùng trong action 'loop'
        tuong_target = f"images/tuong{(self.worker_index % 5) + 2 }.png"
        shared_battle_script = [
            {"action": "click_image", "target": "images/logo1.png", "timeout": 50, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/off.png", "timeout": 3, "confidence": 0.9,"use_color": True},
            {"action": "click_image", "target1": "images/minimize.png","target2": "images/minimize5.png", "timeout": 20, "confidence": 0.9},
            
            
            {"action": "click_image_if", "target1": "images/sansang5v5.png", "target2": "images/sansang3.png","timeout": 60, "confidence": 0.9},
            {"action": "click_image_if", "target1": "images/sansang5v5.png", "target2": "images/sansang3.png","timeout": 10, "confidence": 0.9},


            {"action": "click_image_if", "target": "images/open.png", "timeout": 50, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            

            # Ví dụ các hành động sau khi vào phòng thành công:
            {
                "action": "loop",
                "count": 2,
                "steps": [
                    {"action": "click_image_if", "target": tuong_target, "timeout": 5, "confidence": 0.7},
                ]
            },
            {"action": "click_coords", "x": 899, "y": 482, "timeout": 3},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 20, "confidence": 0.9},
            
            
            {"action": "wait", "timeout": 7},
            {"action": "click_coords", "x": 22, "y": 129, "timeout": 3},
            {"action": "wait", "timeout": 10},
            # Lặp lại click bản đồ 18 lần, mỗi lần cách nhau khoảng 10 giây
            {
                "action": "loop",
                "count": 11,
                "steps": [
                    {"action": "click_image", "target": "images/bienve.png", "timeout": 200, "confidence": 0.9},
                    {"action": "wait", "timeout": 15}
                ]
            },

            {"action": "wait", "timeout": 6},
            {"action": "click_coords", "x": 20, "y": 130, "timeout": 2},
            {"action": "sync_autowin", "timeout": 120},
            
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/victory.png", "timeout": 120, "confidence": 0.9},
            {"action": "wait", "timeout": 30},
            {"action": "click_image_if", "target": "images/victory.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 4},
            {"action": "click_image", "target": "images/tiep_tuc1.png", "timeout": 120, "confidence": 0.9},
            {"action": "wait", "timeout": 4},
            {"action": "click_image", "target": "images/tiep_tuc2.png", "timeout": 120, "confidence": 0.9},
            {"action": "click_any", "wait": 4},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 4, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 4, "confidence": 0.9},
            {"action": "click_coords", "x": 476, "y": 498, "timeout": 3},
            {"action": "click_coords", "x": 459, "y": 36, "timeout": 3},
            {"action": "click_image_if", "target": "images/x4.png", "timeout": 4, "confidence": 0.9},

            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/daulai.png", "timeout": 20, "confidence": 0.9},
            
            # {"action": "press_esc", "wait": 5} ,
            {"action": "click_image_if", "target": "images/close.png", "timeout": 10, "confidence": 0.9},
           
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 3, "confidence": 0.9},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images/huy.png", "timeout": 3, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            
        ]
        
        # GIAI ĐĂNG XUẤT - XUẤT FILE
        uplevel_script = [
            {"action": "click_image", "target": "images/logo1.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/off.png", "timeout": 30, "confidence": 0.9,"use_color": True},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/home.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/cai_dat_button.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/logout.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/ok.png", "timeout": 30, "confidence": 0.9},
            {"action": "wait", "timeout": 15},    
        ]

        while self.running:
            self.modes = self.modes_func() if callable(self.modes_func) else self.modes_func

            # GHÉP SCRIPT DỰA TRÊN LỰA CHỌN MỚI NHẤT
            self.script = []
            if self.modes.get("login"):
                self.script += login_script
            if self.modes.get("tutorial"):
                self.script += tutorial_script
            if self.modes.get("buy_exp"):
                self.script += mua_exp_script
            if self.modes.get("dinh_game"):
                self.script += dinh_game_script

            # 4. GIAI ĐOẠN GHÉP ĐỘI & ĐÁNH TRẬN
            if self.modes.get("teamup"):
                if self.worker_index % 5 == 0:
                    self.script += teamup_host_script
                else:
                    self.script += teamup_guest_script
                    
                wait_step = {"action": "wait_for_players", "count": 4, "timeout": 300}
                self.script.append(wait_step)
                
                battle_loop = {
                    "action": "loop", 
                    "count": self.modes.get("battle_count", 3),
                    "steps": shared_battle_script
                }
                self.script.append(battle_loop)

            # LUÔN CHẠY CUỐI CÙNG SAU KHI XONG HẾT
            self.script += uplevel_script
            # Tìm tài khoản chưa dùng
            self.current_account = None
            with FILE_LOCK:
                for acc in self.accounts_list:
                    if not acc.get("used"):
                        acc["used"] = True
                        self.current_account = acc
                        self.update_ui_func()
                        break
            
            if not self.current_account:
                self.log("HẾT TÀI KHOẢN ĐỂ CHẠY.")
                self.running = False
                break

            self.log(f">> BẮT ĐẦU VÒNG: Acc {self.current_account['tk']}")
            
            # Host reset dữ liệu nhóm khi bắt đầu acc mới
            if self.worker_index % 5 == 0:
                with self.shared_data["lock"]:
                    if "room_ids" in self.shared_data and self.group_id in self.shared_data["room_ids"]:
                        del self.shared_data["room_ids"][self.group_id]
                    if "joined_counts" in self.shared_data:
                        self.shared_data["joined_counts"][self.group_id] = 0

            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step):
                    self.log("THẤT BẠI: Quá thời gian. Đang thử lại...")
                    success = False
                    break
            
            if success and self.running:
                self.update_ui_func()
                self.accounts_processed += 1
                self.report_stats_func(True, self.current_account) # Report Success
            elif not success and self.running:
                self.accounts_processed += 1
                self.report_stats_func(False, self.current_account) # Report Failure
            
            # Tự động Restart sau N lượt chạy
            if self.accounts_processed >= self.restart_threshold:
                self.log(f"Đã chạy {self.accounts_processed} lượt. Tiến hành Restart để sạch RAM.")
                self.restart_emulator()
                self.accounts_processed = 0

            if success and self.running:
                # NẾU CHỈ CHỌN LOGIN: Dừng luôn, không đổi tài khoản tiếp theo
                # Kiểm tra tất cả các mode khác, nếu không có cái nào active ngoài login thì mới dừng
                other_modes_active = any([self.modes.get("tutorial"), self.modes.get("buy_exp"), self.modes.get("dinh_game"), self.modes.get("teamup")])
                if self.modes.get("login") and not other_modes_active:
                    self.log("CHẾ ĐỘ CHỈ LOGIN: Hoàn tất 1 tài khoản và dừng lại.")
                    self.running = False
                    break
            
            time.sleep(1)
            # Dọn dẹp bộ nhớ Python triệt để
            gc.collect()
        
        self.update_status("Xong")
        self.running = False

# --- Modern UI (Premium Edition) ---

class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvLQTool(LD)")
        self.geometry("1000x650")
        self.configure(fg_color=BG_COLOR)
        
        self.accounts_data = []
        self.account_file_path = None # Đường dẫn file tài khoản đang nạp
        self.instances = [] # Danh sách các máy thực tế đang chạy ADB
        self.active_workers = [] # Các thread đang chạy
        self.adb_path = self.find_adb()
        self.ld_path = r"C:\LDPlayer\LDPlayer9\ldconsole.exe" # Mặc định
        
        # Stats Data
        self.success_count = 0
        self.failure_count = 0
        self.start_timestamp = None
        
        # Shared state cho việc ghép đội (Team Up)
        self.shared_data = {
            "room_id": None,
            "joined_count": 0,
            "room_ids": {},
            "joined_counts": {},
            "lock": threading.Lock()
        }
        self.device_map = {} # serial -> absolute_index (0, 1, 2...)

        # Assets (Sử dụng resource_path để đóng gói)
        self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(64, 64))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(25, 25))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(25, 25))

        self.setup_layout()
        self.load_config() # Tải đường dẫn đã lưu
        self.scan_devices()
        
        # Tải sẵn mô hình OCR trong luồng nền để tránh lag khi quét ID phòng lần đầu
        threading.Thread(target=init_ocr_reader, args=(self.add_log,), daemon=True).start()

    def find_adb(self):
        paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
        for p in paths:
            try:
                subprocess.run([p, "version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return p
            except: continue
        return "adb"

    def setup_layout(self):
        # 1. Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=NAV_COLOR)
        self.sidebar.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=(20,0))
        self.logo_label = ctk.CTkLabel(self.sidebar, text="BẢNG ĐIỀU KHIỂN", font=ctk.CTkFont(size=18, weight="bold"), text_color=ACCENT_GREEN)
        self.logo_label.pack(pady=(10, 0))
        ctk.CTkLabel(self.sidebar, text="MegaUpLvLQTool(LD) v2.5", font=ctk.CTkFont(size=11)).pack(pady=(0, 15))

        # LDPlayer Path Config
        self.path_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10)
        self.path_card.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.path_card, text="ĐƯỜNG DẪN LDPLAYER", font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(5, 0))
        self.ld_path_entry = ctk.CTkEntry(self.path_card, placeholder_text=r"Ví dụ: C:\LDPlayer\LDPlayer9", height=28)
        self.ld_path_entry.pack(padx=10, pady=5, fill="x")
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        ctk.CTkButton(self.path_card, text="Lưu Đường Dẫn", command=self.save_config, height=22, font=ctk.CTkFont(size=11)).pack(padx=10, pady=(0, 5), fill="x")

        # Restart Threshold config
        ctk.CTkLabel(self.path_card, text="LƯỢT CHẠY RESTART (CYCLES)", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10, 0))
        self.restart_threshold_entry = ctk.CTkEntry(self.path_card, placeholder_text="Mặc định: 3", height=30)
        self.restart_threshold_entry.pack(padx=10, pady=5, fill="x")
        self.restart_threshold_entry.insert(0, "3")

        # Account Card
        self.account_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333333")
        self.account_card.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.account_card, text="TÀI KHOẢN", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=2)
        ctk.CTkButton(self.account_card, text="NẠP FILE", command=self.load_accounts, fg_color="#EAB308", text_color="#000", height=30).pack(padx=15, pady=(0, 10), fill="x")


        # Control (Packed from bottom)
        ctk.CTkLabel(self.sidebar, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=11), text_color="#666").pack(side="bottom", pady=10)
        self.btn_stop = ctk.CTkButton(self.sidebar, text=" DỪNG TẤT CẢ", image=self.stop_icon, compound="left", command=self.stop_all, fg_color="#333", height=40, corner_radius=10)
        self.btn_stop.pack(side="bottom", padx=20, pady=5, fill="x")
        self.btn_start = ctk.CTkButton(self.sidebar, text=" CHẠY TẤT CẢ", image=self.start_icon, compound="left", command=self.start_all, height=40, corner_radius=10, font=ctk.CTkFont(size=14, weight="bold"))
        self.btn_start.pack(side="bottom", padx=20, pady=5, fill="x")



        # 2. Main Area
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.pack(side="right", fill="both", expand=True, padx=25, pady=25)

        # Instance Selection Card
        self.inst_frame = ctk.CTkFrame(self.main_content, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333")
        self.inst_frame.pack(fill="x", pady=(0, 20))
        inst_header = ctk.CTkFrame(self.inst_frame, fg_color="transparent")
        inst_header.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(inst_header, text="THIẾT BỊ ĐANG MỞ", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN).pack(side="left")

        # Action Buttons for Instances
        btns_frame = ctk.CTkFrame(inst_header, fg_color="transparent")
        btns_frame.pack(side="right")
        # Nút chọn tất cả được gỡ bỏ vì người dùng muốn chạy tất cả máy mà không cần check
        ctk.CTkButton(btns_frame, text="Làm Mới Danh Sách", command=self.scan_devices, height=26, width=120, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=5)

        self.device_list_frame = ctk.CTkScrollableFrame(self.inst_frame, height=180, fg_color="transparent") 
        self.device_list_frame.pack(fill="x", padx=10, pady=(0, 15))
        # Tăng số cột lên 10 để thu gọn cho nhiều máy
        for col in range(10): 
            self.device_list_frame.grid_columnconfigure(col, weight=1)
        self.device_cards = {}
        self.team_frames = {}


        # Queue and Logs
        self.mid_grid = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.mid_grid.pack(fill="both", expand=True)
        self.mid_grid.grid_columnconfigure(0, weight=1)
        self.mid_grid.grid_rowconfigure(0, weight=1)

        # Stats Dashboard
        self.stats_card = ctk.CTkFrame(self.mid_grid, fg_color=CARD_COLOR, corner_radius=15)
        self.stats_card.grid(row=0, column=0, sticky="nsew")
        
        # Mode Selection (Moved from Sidebar)
        modes_title = ctk.CTkLabel(self.stats_card, text="CHẾ ĐỘ HOẠT ĐỘNG", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_GREEN)
        modes_title.pack(pady=(12, 5))
        
        self.mode_frame = ctk.CTkFrame(self.stats_card, fg_color="transparent")
        self.mode_frame.pack(fill="x", padx=15, pady=5)
        self.mode_frame.columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.mode_login = ctk.CTkCheckBox(self.mode_frame, text="LOGIN", font=ctk.CTkFont(size=11))
        self.mode_login.grid(row=0, column=0); self.mode_login.select()

        self.mode_tutorial = ctk.CTkCheckBox(self.mode_frame, text="TÂN THỦ", font=ctk.CTkFont(size=11))
        self.mode_tutorial.grid(row=0, column=1); self.mode_tutorial.select()

        self.mode_buy_exp = ctk.CTkCheckBox(self.mode_frame, text="OFF LÂU (LV8)", font=ctk.CTkFont(size=11), text_color="#EAB308")
        self.mode_buy_exp.grid(row=0, column=2); self.mode_buy_exp.select()

        self.mode_dinh_game = ctk.CTkCheckBox(self.mode_frame, text="DÍNH GAME", font=ctk.CTkFont(size=11), text_color="#F59E0B")
        self.mode_dinh_game.grid(row=0, column=3); self.mode_dinh_game.select()

        self.mode_teamup = ctk.CTkCheckBox(self.mode_frame, text="GHÉP ĐỘI", font=ctk.CTkFont(size=11), text_color=ACCENT_GREEN)
        self.mode_teamup.grid(row=0, column=4); self.mode_teamup.select()



        ctk.CTkLabel(self.stats_card, text="THÔNG SỐ THỜI GIAN THỰC", font=ctk.CTkFont(size=12, weight="bold"), text_color="#888").pack(pady=(15, 5))
        
        self.stats_inner = ctk.CTkFrame(self.stats_card, fg_color="transparent")
        self.stats_inner.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.stats_inner.columnconfigure((0, 1), weight=1)

        self.success_val = self.create_stat_item(self.stats_inner, "THÀNH CÔNG", "0", 0, 0, "#4ADE80")
        self.active_device_val = self.create_stat_item(self.stats_inner, "ĐANG CHẠY", "0", 0, 1, "#00D2FF")
        self.lag_val = self.create_stat_item(self.stats_inner, "LAG", "0", 1, 0, "#EF4444")
        self.total_devices_val = self.create_stat_item(self.stats_inner, "TỔNG MÁY", "0", 1, 1, "#888")
        self.total_accounts_val = self.create_stat_item(self.stats_inner, "TỔNG ACC", "0", 2, 0, "#888")

        # Battle count field (Required for start_team logic)
        ctk.CTkLabel(self.stats_card, text="SỐ TRẬN BATTLE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888").pack(pady=(12, 0))
        self.battle_count_entry = ctk.CTkEntry(self.stats_card, placeholder_text="Mặc định: 5", height=28)
        self.battle_count_entry.pack(padx=15, pady=5, fill="x")
        self.battle_count_entry.insert(0, "3")


    def create_stat_item(self, parent, title, value, row, col, color):
        frame = ctk.CTkFrame(parent, fg_color="#252525", corner_radius=6, height=30)
        frame.grid(row=row, column=col, padx=3, pady=2, sticky="nsew")
        frame.grid_propagate(False)
        
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=9, weight="bold"), text_color="#888").pack(side="left", padx=10)
        val_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=12, weight="bold"), text_color=color)
        val_label.pack(side="right", padx=10)
        return val_label

    def report_stats(self, success=True, account=None):
        def _update():
            if success:
                self.success_count += 1
                if account: self.export_account(account, "SUCCESS_ACC.txt")
            else:
                self.failure_count += 1
                if account: self.export_account(account, "FAILED_ACC.txt")
            
            # Xóa tài khoản khỏi file nguồn khi hoàn thành (Dù thành công hay thất bại)
            if account:
                self.remove_account_from_file(account)
                
            self.update_stats_ui()
        self.after(0, _update)

    def remove_account_from_file(self, account):
        if not hasattr(self, "account_file_path") or not self.account_file_path or not os.path.exists(self.account_file_path):
            return
        
        acc_str = f"{account['tk']}|{account['mk']}"
        with FILE_LOCK:
            try:
                # Đọc toàn bộ nội dung
                with open(self.account_file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                # Ghi lại những dòng không trùng với acc vừa chạy
                with open(self.account_file_path, "w", encoding="utf-8") as f:
                    for line in lines:
                        if line.strip() != acc_str:
                            f.write(line)
                self.add_log(f"Đã xóa acc {account['tk']} khỏi file nguồn.")
            except Exception as e:
                self.add_log(f"LỖI XÓA ACC TRONG FILE: {e}")

    def export_account(self, account, filename):
        try:
            with FILE_LOCK:
                with open(filename, "a", encoding="utf-8") as f:
                    f.write(f"{account['tk']}|{account['mk']}\n")
        except Exception as e:
            self.add_log(f"LỖI XUẤT FILE: {e}")

    def update_stats_ui(self):
        self.success_val.configure(text=str(self.success_count))
        active = sum(1 for w in self.active_workers if w.running)
        self.active_device_val.configure(text=str(active))
        lags = sum(1 for w in self.active_workers if w.is_lagging)
        self.lag_val.configure(text=str(lags))
        self.total_devices_val.configure(text=str(len(self.device_cards)))
        self.total_accounts_val.configure(text=str(len(self.accounts_data)))

    def update_team_status(self, team_idx):
        if team_idx not in self.team_frames: return
        team_data = self.team_frames[team_idx]
        devices = team_data["devices"]
        active_in_team = sum(1 for w in self.active_workers if w.running and hasattr(w, 'device_id') and w.device_id in devices)
        total_in_team = len(devices)
        if active_in_team > 0:
            team_data["start_btn"].configure(text=f"RUNNING ({active_in_team}/{total_in_team})", state="disabled", fg_color="#FFA500")
            team_data["stop_btn"].configure(state="normal", fg_color="#ef4444")
        else:
            team_data["start_btn"].configure(text="START", state="normal", fg_color="#10b981")
            team_data["stop_btn"].configure(state="disabled", fg_color="#333")

    def update_all_ui(self):
        def _update():
            self.update_stats_ui()
            for team_idx in self.team_frames:
                self.update_team_status(team_idx)
        self.after(0, _update)

    def save_config(self):
        config = {
            "ld_path": self.ld_path_entry.get().strip(),
            "restart_threshold": self.restart_threshold_entry.get().strip()
        }
        with open("config.json", "w") as f:
            json.dump(config, f)
        self.add_log("HỆ THỐNG: Đã lưu cấu hình LDPlayer và Lượt Restart.")

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                    path = config.get("ld_path", "")
                    if path:
                        self.ld_path_entry.delete(0, "end")
                        self.ld_path_entry.insert(0, path)
                    
                    restart_threshold = config.get("restart_threshold", "")
                    if restart_threshold:
                        self.restart_threshold_entry.delete(0, "end")
                        self.restart_threshold_entry.insert(0, restart_threshold)
            except: pass

    def get_absolute_index(self, serial):
        """Xác định số thứ tự máy (0, 1, 2...) dựa trên port ADB"""
        port = None
        if "emulator-" in serial:
            try: port = int(serial.split("-")[1])
            except: pass
        elif ":" in serial:
            try: port = int(serial.split(":")[1])
            except: pass
            
        if port is not None:
            # LDPlayer logic: port 5554/5555 là máy 0 (máy 1), 5556/5557 là máy 1...
            if port >= 5554:
                if port % 2 == 0: return (port - 5554) // 2
                else: return (port - 5555) // 2
        return -1

    def scan_devices(self):
        base_path = self.ld_path_entry.get().strip()
        self.adb_path = os.path.join(base_path, "adb.exe")
        if not os.path.exists(self.adb_path): self.adb_path = "adb"
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        self.team_frames = {}
        self.device_map = {}
        try:
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            lines = res.stdout.strip().split('\n')[1:]
            device_serials = [line.split('\t')[0] for line in lines if "device" in line]
            
            # Lấy tất cả serials và gán index dựa trên port ADB để sắp xếp
            # Việc sắp xếp giúp thứ tự máy ổn định (máy index thấp luôn đứng trước)
            serials_with_idx = []
            for serial in device_serials:
                abs_idx = self.get_absolute_index(serial)
                serials_with_idx.append((serial, abs_idx))
            
            # Sắp xếp theo LD index tăng dần
            serials_with_idx.sort(key=lambda x: x[1])
            
            # Gán worker_index (0, 1, 2...) theo thứ tự đã sắp xếp
            for i, (serial, abs_idx) in enumerate(serials_with_idx):
                self.device_map[serial] = i
                machine_num = abs_idx + 1 if abs_idx != -1 else "?? "
                self.add_log(f"Thiết bị: {serial} -> Index: {i} (LD Máy: {machine_num})")
            
            if not self.device_map:
                self.add_log("CẢNH BÁO: Không tìm thấy thiết bị nào.")
                return

            # Gom nhóm theo Team (0-4: Team 1, 5-9: Team 2...)
            teams_data = {}
            for serial, abs_idx in self.device_map.items():
                team_idx = abs_idx // 5
                if team_idx not in teams_data: teams_data[team_idx] = []
                teams_data[team_idx].append(serial)
                
            # Hiển thị các Team đã gom nhóm
            for team_idx in sorted(teams_data.keys()):
                team_frame = ctk.CTkFrame(self.device_list_frame, fg_color="#1a1a1a", corner_radius=6, border_width=1, border_color="#333")
                team_frame.pack(pady=2, padx=5, fill="x")
                
                # Header Team + Nút
                header_row = ctk.CTkFrame(team_frame, fg_color="transparent", height=24)
                header_row.pack(fill="x", padx=5, pady=2)
                header_row.pack_propagate(False)

                ctk.CTkLabel(header_row, text=f"T{team_idx + 1}", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_GREEN).pack(side="left", padx=2)
                
                btn_stop_team = ctk.CTkButton(header_row, text="STOP", command=lambda t=team_idx: self.stop_team(t), fg_color="#ef4444", hover_color="#dc2626", height=18, width=50, font=ctk.CTkFont(size=10, weight="bold"))
                btn_stop_team.pack(side="right", padx=2)
                
                btn_start_team = ctk.CTkButton(header_row, text="START", command=lambda t=team_idx: self.start_team(t), fg_color="#10b981", hover_color="#059669", height=18, width=50, font=ctk.CTkFont(size=10, weight="bold"))
                btn_start_team.pack(side="right", padx=2)

                devices_frame = ctk.CTkFrame(team_frame, fg_color="transparent")
                devices_frame.pack(fill="x", padx=5, pady=(0, 3))
                devices_frame.columnconfigure(list(range(5)), weight=1)
                
                current_team_devices = sorted(teams_data[team_idx], key=lambda s: self.device_map[s])
                
                for i, serial in enumerate(current_team_devices):
                    abs_idx = self.device_map[serial]
                    is_host = (abs_idx % 5 == 0)
                    
                    card_color = "#2d3748" if is_host else "#252525"
                    border_color = ACCENT_GREEN if is_host else "#383838"
                    
                    card = ctk.CTkFrame(devices_frame, fg_color=card_color, corner_radius=4, border_width=1, border_color=border_color, height=20)
                    card.grid(row=0, column=i, padx=1, pady=1, sticky="nsew"); card.grid_propagate(False)
                    
                    lbl_text = f"M{abs_idx + 1}"
                    ctk.CTkLabel(card, text=lbl_text, font=ctk.CTkFont(size=10, weight="bold" if is_host else "normal")).pack(expand=True)
                    
                    status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=1))
                    self.device_cards[serial] = {"card": card, "status": status_lbl}
                
                self.team_frames[team_idx] = {"frame": team_frame, "devices": current_team_devices, "start_btn": btn_start_team, "stop_btn": btn_stop_team}
            
            self.update_stats_ui()
        except Exception as e:
            self.add_log(f"LỖI: Không thể quét thiết bị: {e}")

    def load_accounts(self):
        file_path = fd.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not file_path: return
        self.account_file_path = file_path
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    parts = line.split('|', 1)
                    if len(parts) >= 2:
                        self.accounts_data.append({"tk": parts[0], "mk": parts[1], "used": False})
            
            self.update_stats_ui()
            self.add_log(f"HỆ THỐNG: Đã nạp {len(self.accounts_data)} tài khoản từ file .txt.")
        except Exception as e:
            self.add_log(f"LỖI ĐỌC FILE: {e}")

    def add_log(self, text):
        # Only print to console, no UI log
        try:
            print(f"DEBUG: {text}")
        except UnicodeEncodeError:
            print(f"DEBUG: {text.encode('utf-8', errors='replace').decode('utf-8')}")

    def start_all(self):
        if not self.team_frames:
            self.add_log("LỖI: Không tìm thấy team nào. Hãy quét thiết bị trước.")
            return
        if not self.accounts_data:
            self.add_log("LỖI: Danh sách tài khoản đang trống.")
            return

        self.btn_start.configure(state="disabled", text=" ĐANG CHẠY...")
        self.btn_stop.configure(state="normal", fg_color=ACCENT_RED)
        
        # Reset Stats
        self.success_count = 0
        self.failure_count = 0
        self.start_timestamp = time.time()
        self.update_stats_ui()

        # Start all teams
        for team_idx in self.team_frames:
            self.start_team(team_idx)

    def stop_all(self):
        self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")
        self.btn_stop.configure(state="disabled", fg_color="#333")
        
        # Stop all teams
        for team_idx in self.team_frames:
            self.stop_team(team_idx)
        
        self.add_log("!!! ĐANG DỪNG TẤT CẢ CÁC MÁY...")

    def get_current_modes(self):
        try:
            b_count = int(self.battle_count_entry.get().strip())
        except:
            b_count = 3
        return {
            "login": self.mode_login.get(),
            "tutorial": self.mode_tutorial.get(),
            "buy_exp": self.mode_buy_exp.get(),
            "dinh_game": self.mode_dinh_game.get(),
            "teamup": self.mode_teamup.get(),
            "battle_count": b_count,
        }

    def start_team(self, team_idx):
        if team_idx not in self.team_frames:
            return
        team_data = self.team_frames[team_idx]
        devices = team_data["devices"]
        if not devices:
            self.add_log(f"LỖI: Team {team_idx + 1} không có thiết bị.")
            return
        if not self.accounts_data:
            self.add_log("LỖI: Danh sách tài khoản đang trống.")
            return

        team_data["start_btn"].configure(state="disabled")
        team_data["stop_btn"].configure(state="normal", fg_color=ACCENT_RED)

        # Chạy đa luồng cho các máy trong team
        for serial in devices:
            worker_index = self.device_map.get(serial, 0) # Lấy absolute index đã lưu
            worker = AutoClickerInstance(serial, self.adb_path, self.add_log, self.update_all_ui, self.report_stats)
            
            base_ld_path = self.ld_path_entry.get().strip()
            worker.ld_console_path = base_ld_path if base_ld_path.endswith(".exe") else os.path.join(base_ld_path, "ldconsole.exe")
            try:
                worker.restart_threshold = int(self.restart_threshold_entry.get().strip())
            except:
                worker.restart_threshold = 3
                
            self.active_workers.append(worker)
            t = threading.Thread(target=worker.run, args=(self.accounts_data, self.get_current_modes, worker_index, self.shared_data), daemon=True)
            t.start()

        self.add_log(f"!!! ĐANG KHỞI ĐỘNG TEAM {team_idx + 1}...")
        self.update_team_status(team_idx)

    def stop_team(self, team_idx):
        if team_idx not in self.team_frames:
            return
        team_data = self.team_frames[team_idx]
        team_data["start_btn"].configure(state="normal")
        team_data["stop_btn"].configure(state="disabled", fg_color="#333")
        
        # Stop workers in this team
        for w in self.active_workers[:]:  # Copy list to avoid modification during iteration
            if hasattr(w, 'group_id') and w.group_id == team_idx:
                w.running = False
                self.active_workers.remove(w)
        
        self.add_log(f"!!! ĐANG DỪNG TEAM {team_idx + 1}...")
        self.update_team_status(team_idx)

    def activate(self):
        key = self.key_input.get().strip()
        if not key:
            self.status_label.configure(text="Vui lòng nhập Key!")
            return
        
        valid, msg = verify_license(key, self.hwid)
        if valid:
            with open(LICENSE_FILE, "w") as f:
                f.write(key)
            self.status_label.configure(text=f"Kích hoạt thành công! Hạn dùng: {msg}", text_color="#4ADE80")
            self.after(1500, self.launch_main)
        else:
            self.status_label.configure(text=msg, text_color=ACCENT_RED)

def get_hwid():
    try:
        def get_cmd(cmd):
            try:
                # Sử dụng shell=True và lọc kết quả sạch hơn
                res = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
                lines = [l.strip() for l in res.split('\n') if l.strip()]
                if len(lines) > 1:
                    val = lines[1].strip()
                    # Loại bỏ các giá trị rác phổ biến của nhà sản xuất thường gây trùng mã
                    trash = ["filled", "default", "none", "00000000", "ffffffff", "unknown", "to be"]
                    if any(t in val.lower() for t in trash): return ""
                    return val
                return ""
            except: return ""

        # 1. BIOS UUID (Thường bị trùng trên máy ảo clone)
        hw_uuid = get_cmd("wmic csproduct get uuid")
        # 2. Disk Serial (Ổ cứng đầu tiên)
        disk_serial = get_cmd("wmic diskdrive where 'index=0' get serialnumber")
        # 3. CPU ID
        cpu_id = get_cmd("wmic cpu get processorid")
        # 4. Mainboard Serial (Rất khó trùng trên máy thật)
        board_serial = get_cmd("wmic baseboard get serialnumber")
        
        # 5. Machine GUID (Duy nhất cho mỗi bộ Windows cài đặt)
        machine_guid = ""
        if winreg:
            try:
                registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
                machine_guid, _ = winreg.QueryValueEx(registry_key, "MachineGuid")
                winreg.CloseKey(registry_key)
            except: pass

        # 6. MAC Address (Dùng làm định danh bổ trợ)
        mac = str(uuid.getnode())

        # Kết hợp tất cả các nguồn dữ liệu để tạo mã băm 20 ký tự
        combined = f"U:{hw_uuid}|D:{disk_serial}|C:{cpu_id}|B:{board_serial}|G:{machine_guid}|M:{mac}"
        return hashlib.sha256(combined.encode()).hexdigest()[:20].upper()
    except:
        # Fallback an toàn nếu toàn bộ các lệnh trên lỗi
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:20].upper()

def verify_license(key, hwid):
    try:
        # Format key: Base64(ExpiryTimestamp|Signature)
        decoded = base64.b64decode(key).decode()
        expiry_str, signature = decoded.split('|')
        
        # Kiểm tra Signature
        expected_sig = hashlib.sha256(f"{expiry_str}{hwid}{SECRET_KEY}".encode()).hexdigest()[:10]
        if signature != expected_sig:
            return False, "Key không hợp lệ cho máy này!"
        
        # Kiểm tra Hạn dùng (Chính xác đến từng giây)
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_date:
            return False, f"Key đã hết hạn vào {expiry_str}!"
            
        return True, expiry_str
    except:
        return False, "Key sai định dạng!"


class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KÍCH HOẠT MegaUpLvLQTool")
        self.geometry("500x550")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        
        self.hwid = get_hwid()
        self.setup_ui()

    def setup_ui(self):
        # Logo & Title
        ctk.CTkLabel(self, text="MegaUpLvLQTool(LD)", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(40, 10))
        ctk.CTkLabel(self, text="HỆ THỐNG QUẢN LÝ BẢN QUYỀN", font=ctk.CTkFont(size=12)).pack(pady=(0, 30))

        # HWID Box
        hwid_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        hwid_frame.pack(padx=40, fill="x")
        ctk.CTkLabel(hwid_frame, text="MÃ MÁY CỦA BẠN (HWID):", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10, 0))
        
        # Dùng Entry để dễ copy
        self.hwid_entry = ctk.CTkEntry(hwid_frame, placeholder_text=self.hwid, height=35, font=ctk.CTkFont(size=12))
        self.hwid_entry.insert(0, self.hwid)
        self.hwid_entry.configure(state="readonly")
        self.hwid_entry.pack(padx=20, pady=(5, 10), fill="x")
        
        ctk.CTkLabel(self, text="Hãy gửi mã trên cho Admin để nhận Key kích hoạt.", font=ctk.CTkFont(size=10), text_color="#888").pack(pady=5)

        # Key Input
        self.key_input = ctk.CTkEntry(self, placeholder_text="Nhập Key kích hoạt tại đây...", height=40)
        self.key_input.pack(padx=40, pady=20, fill="x")

        # Buttons
        self.btn_activate = ctk.CTkButton(self, text="KÍCH HOẠT NGAY", command=self.activate, height=45, corner_radius=10, font=ctk.CTkFont(weight="bold"))
        self.btn_activate.pack(padx=40, pady=5, fill="x")
        
        self.status_label = ctk.CTkLabel(self, text="", text_color=ACCENT_RED)
        self.status_label.pack(pady=10)

        # Footer Credit (Nguồn)
        ctk.CTkLabel(self, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=12, weight="bold"), text_color="#777").pack(pady=(30, 20))

    def activate(self):
        key = self.key_input.get().strip()
        if not key:
            self.status_label.configure(text="Vui lòng nhập Key!")
            return
        
        valid, msg = verify_license(key, self.hwid)
        if valid:
            with open(LICENSE_FILE, "w") as f:
                f.write(key)
            self.status_label.configure(text=f"Kích hoạt thành công! Hạn dùng: {msg}", text_color="#4ADE80")
            self.after(1500, self.launch_main)
        else:
            self.status_label.configure(text=msg, text_color=ACCENT_RED)

    def launch_main(self):
        self.destroy()
        main_app = MultiPremiumApp()
        main_app.mainloop()


if __name__ == "__main__":
    hwid = get_hwid()
    need_login = True
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            saved_key = f.read().strip()
        valid, _ = verify_license(saved_key, hwid)
        if valid:
            need_login = False
    
    if need_login:
        login = LoginApp()
        login.mainloop()
    else:
        app = MultiPremiumApp()
        app.mainloop()

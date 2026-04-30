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

# Ensure console output uses UTF-8
try:
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
except: pass

# --- Fix WinError 1114 & SSL for torch/easyocr ---
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except: pass

if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    _internal = os.path.join(_meipass, '_internal')
    for dp in [_meipass, _internal, os.path.join(_internal, 'torch', 'lib')]:
        if os.path.exists(dp):
            if hasattr(os, 'add_dll_directory'):
                try: os.add_dll_directory(dp)
                except: pass
            os.environ['PATH'] = dp + os.pathsep + os.environ.get('PATH', '')
    # Force load OpenMP to avoid 1114 conflict
    try:
        import ctypes
        ctypes.CDLL(os.path.join(_internal, 'torch', 'lib', 'libiomp5md.dll'))
    except: pass

import tkinter.filedialog as fd

# --- Biến toàn cục để nạp OCR ---
easyocr = None
_ocr_reader = None
SECRET_KEY = "RyoUTE_MegaUpLvLQ_BoxPhone_2026"
LICENSE_FILE = "license_boxphone.bin"

def init_ocr_reader(log_func=None):
    global easyocr, _ocr_reader
    if _ocr_reader is not None:
        return _ocr_reader
    try:
        if log_func: log_func("Đang nạp bộ xử lý OCR cho BoxPhone...")
        import easyocr as ocr_lib
        try:
            import torch
            torch.set_num_threads(1)
        except: pass
        easyocr = ocr_lib
        _reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        _ocr_reader = _reader
        if log_func: log_func("Nạp OCR thành công.")
        return _ocr_reader
    except Exception as e:
        if log_func: log_func(f"LỖI OCR: {str(e)}")
        return None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class StdoutRedirector:
    def __init__(self, log_func):
        self.log_func = log_func
    def write(self, s):
        if s.strip():
            self.log_func(s.strip())
    def flush(self):
        pass

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

# Độ phân giải gốc mà ảnh được chụp (Phải đúng kích thước ảnh trong thư mục images)
BASE_WIDTH = 960.0
BASE_HEIGHT = 540.0

# --- Global Cache for Template Images ---
IMAGE_CACHE = {}

def get_cached_template(t_path, use_color=False):
    key = (t_path, use_color)
    if key not in IMAGE_CACHE:
        real_path = resource_path(t_path)
        if not os.path.exists(real_path):
            return None
        mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
        img = cv2.imread(real_path, mode)
        IMAGE_CACHE[key] = img
    return IMAGE_CACHE[key]

def extract_device_number(serial):
    """Trích xuất số từ serial (ví dụ: 192.168.1.61 -> 61, box61 -> 61)"""
    nums = re.findall(r'\d+', serial)
    if nums:
        # Lấy số cuối cùng thường là định danh máy
        return int(nums[-1])
    return None

class AutoClickerInstance:
    def __init__(self, device_id, device_index, is_host, adb_path, log_func, update_ui_func, report_stats_func):
        self.device_id = device_id
        self.device_index = device_index # 0-based
        self.is_host = is_host
        self.adb_path = adb_path
        self.log_func = log_func
        self.update_ui_func = update_ui_func
        self.report_stats_func = report_stats_func
        self.running = False
        self.status = "Đang chờ"
        self.last_step_time = time.time()
        self.is_lagging = False
        self.script = []
        self.current_account = None
        self.modes = {}
        self.accounts_processed = 0
        self.restart_threshold = 10 
        self.template_cache = {} # Cache cho các ảnh mẫu đã được resize theo scale của máy này

    def log(self, msg):
        self.log_func(f"[Máy {self.device_index + 1}] {msg}")

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
        # Dự phòng cho các hàm vẫn gọi escape_adb_text trực tiếp
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
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self):
        try:
            # Thử dùng exec-out trước với timeout ngắn (5s) để xem ADB có hỗ trợ không
            cmd = [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"]
            try:
                process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                if process.returncode != 0:
                    raise Exception("Lỗi exec-out")
                image_bytes = process.stdout
            except Exception:
                # Nếu timeout hoặc báo lỗi (do ADB của Xiaowei không hỗ trợ exec-out), chuyển sang shell
                cmd_fallback = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
                process = subprocess.run(cmd_fallback, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                image_bytes = process.stdout.replace(b"\r\n", b"\n")

            if not image_bytes:
                self.log("LỖI: Trống dữ liệu ảnh từ thiết bị.")
                return None
                
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            if img is None:
                self.log("LỖI: Không thể giải mã ảnh (imdecode fail).")
            return img
        except Exception as e:
            self.log(f"LỖI Chụp màn hình: {str(e)}")
            return None


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
                for sub_step in step.get("then", []):
                    if not self.execute_step(sub_step): break
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
        elif action == "click_coords":
            res = self.click_coords_logic(step)
        elif action == "wait_for_players":
            res = self.wait_for_players_logic(step)
        elif action == "notify_joined":
            res = self.notify_joined_logic()
        elif action == "wait_for_room":
            res = self.wait_for_room_logic(step)
        elif action == "input_room_id":
            res = self.input_room_id_logic()
        elif action == "click_any":
            res = self.click_any_logic(step)
        elif action == "swipe":
            res = self.swipe_logic(step)
        elif action == "press_esc":
            res = self.press_esc_logic(step)
        elif action == "sync_autowin":
            res = self.sync_autowin_logic(step)
        elif action == "buy_exp":
            res = self.buy_exp_logic(step)
        elif action == "cases":
            res = self.cases_logic(step)
        elif action == "loop":
            count = step.get("count", 1)
            sub_steps = step.get("steps", [])
            for i in range(count):
                if not self.running: return False
                self.log(f"--- Lượt {i+1}/{count} ---")
                for s in sub_steps:
                    if not self.execute_step(s): return False
            res = True
        
        duration = time.time() - self.last_step_time
        if duration > 35: self.update_status("Lag", True)
        else: self.update_status("Đang chạy", False)
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
        use_color = step.get("use_color", False)

        # Chuẩn bị ảnh mẫu (Sử dụng Cache)
        target_data = []
        for t_path in targets:
            t_img = get_cached_template(t_path, use_color)
            if t_img is not None:
                target_data.append((t_path, t_img))
            else:
                self.log(f"Thiếu ảnh mẫu: {t_path}")

        start = time.time()
        best_match = {"val": 0, "name": ""}
        last_screen = None
        
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                last_screen = screen
                h_screen, w_screen = screen.shape[:2]
                scale = h_screen / BASE_HEIGHT

                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                
                for t_path, t_img in target_data:
                    # Kiểm tra và tạo ảnh đã resize trong cache của instance
                    # Chỉ quét 2 mức scale quan trọng nhất để tăng tốc: Native và Scaled
                    for curr_scale in [scale, 1.0]:
                        cache_key = (t_path, curr_scale, use_color)
                        if cache_key in self.template_cache:
                            t_scaled = self.template_cache[cache_key]
                        else:
                            if abs(curr_scale - 1.0) < 0.001:
                                t_scaled = t_img
                            else:
                                tw, th = int(t_img.shape[1]*curr_scale), int(t_img.shape[0]*curr_scale)
                                t_scaled = cv2.resize(t_img, (tw, th), interpolation=cv2.INTER_LINEAR)
                            self.template_cache[cache_key] = t_scaled

                        if compare_screen.shape[0] < t_scaled.shape[0] or compare_screen.shape[1] < t_scaled.shape[1]:
                            continue
                            
                        res = cv2.matchTemplate(compare_screen, t_scaled, cv2.TM_CCOEFF_NORMED)
                        _, mv, _, ml = cv2.minMaxLoc(res)
                        
                        if mv > best_match["val"]:
                            best_match = {"val": mv, "name": os.path.basename(t_path)}
                            
                        if mv >= confidence:
                            th_s, tw_s = t_scaled.shape[:2]
                            self.call_adb(["shell", "input", "tap", str(ml[0]+tw_s//2), str(ml[1]+th_s//2)])
                            self.log(f"==> CLICK OK: {os.path.basename(t_path)} ({mv:.2f} @ {curr_scale:.2f}x)")
                            return True
            time.sleep(0.2)
        
        if last_screen is not None:
            cv2.imwrite("debug_fail.png", last_screen)
            self.log("!! Đã lưu ảnh chụp màn hình lỗi vào: debug_fail.png")
            
        self.log(f"!! Timeout: Không thấy ảnh. Cao nhất: {best_match['name']} ({best_match['val']:.2f})")
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
            
            h_screen, w_screen = screen.shape[:2]
            scale = h_screen / BASE_HEIGHT
            
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
                    t_img = get_cached_template(t_path, False)
                    if t_img is None: continue
                    
                    scr_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    
                    for curr_scale in [scale, 1.0]:
                        cache_key = (t_path, curr_scale, False)
                        if cache_key in self.template_cache:
                            t_scaled = self.template_cache[cache_key]
                        else:
                            if abs(curr_scale - 1.0) < 0.001:
                                t_scaled = t_img
                            else:
                                t_scaled = cv2.resize(t_img, (int(t_img.shape[1]*curr_scale), int(t_img.shape[0]*curr_scale)), interpolation=cv2.INTER_LINEAR)
                            self.template_cache[cache_key] = t_scaled
                        
                        if scr_gray.shape[0] < t_scaled.shape[0] or scr_gray.shape[1] < t_scaled.shape[1]:
                            continue
                            
                        res = cv2.matchTemplate(scr_gray, t_scaled, cv2.TM_CCOEFF_NORMED)
                        _, mv, _, _ = cv2.minMaxLoc(res)
                        if mv >= case_conf:
                            self.log(f"-> PHÁT HIỆN: {os.path.basename(t_path)} ({mv:.2f})")
                            for s_step in sub_script:
                                if not self.running: break
                                self.execute_step(s_step)
                            return True 
            time.sleep(0.2)
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

    def search_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        use_color = step.get("use_color", False)
        t_img = get_cached_template(target, use_color)
        if t_img is None: return False
        
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                h_screen, w_screen = screen.shape[:2]
                scale = h_screen / BASE_HEIGHT

                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

                for curr_scale in [scale, 1.0]:
                    cache_key = (target, curr_scale, use_color)
                    if cache_key in self.template_cache:
                        t_scaled = self.template_cache[cache_key]
                    else:
                        if abs(curr_scale - 1.0) < 0.001:
                            t_scaled = t_img
                        else:
                            t_scaled = cv2.resize(t_img, (int(t_img.shape[1]*curr_scale), int(t_img.shape[0]*curr_scale)), interpolation=cv2.INTER_LINEAR)
                        self.template_cache[cache_key] = t_scaled

                    if compare_screen.shape[0] < t_scaled.shape[0] or compare_screen.shape[1] < t_scaled.shape[1]:
                        continue
                        
                    res = cv2.matchTemplate(compare_screen, t_scaled, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    if mv >= conf: return True
            time.sleep(0.2)
        return False

    def click_any_logic(self, step):
        wait_time = step.get("wait") or 0
        if wait_time > 0: time.sleep(wait_time)
        screen = self.get_screenshot()
        if screen is not None:
            h, w = screen.shape[:2]
            self.call_adb(["shell", "input", "tap", str(w//2), str(h//2)])
            return True
        return False

    def swipe_logic(self, step):
        screen = self.get_screenshot()
        h, w = (screen.shape[:2]) if screen is not None else (540, 960)
        def gv(v, m): return int(v*m) if isinstance(v, float) and v <= 1.0 else int(v)
        x1, y1 = gv(step.get("x1", 0.5), w), gv(step.get("y1", 0.8), h)
        x2, y2 = gv(step.get("x2", 0.5), w), gv(step.get("y2", 0.3), h)
        self.call_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(step.get("duration", 500))])
        return True

    def press_esc_logic(self, step):
        time.sleep(step.get("wait", 0))
        self.call_adb(["shell", "input", "keyevent", "4"])
        return True

    def input_name_logic(self):
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        name = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(7))
        self.call_adb(["shell", "input", "text", self.escape_adb_text(name)])
        return True

    def input_text_logic(self, step):
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        self.input_text_robust(step.get("content", ""))
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
        global _ocr_reader
        reader = init_ocr_reader(self.log)
        if reader is None: return False
        
        # Xóa ID cũ trước khi lấy ID mới
        with self.shared_data["lock"]:
            if self.group_id in self.shared_data["room_ids"]:
                del self.shared_data["room_ids"][self.group_id]
            self.shared_data["joined_counts"][self.group_id] = 1 # Host tự tính là 1

        roi = step.get("roi", [0.50, 0.0, 0.30, 0.10])
        timeout = step.get("timeout", 45)
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None: continue
            h_f, w_f = screen.shape[:2]
            rx, ry, rw, rh = roi
            x1, y1, x2, y2 = int(rx*w_f), int(ry*h_f), int((rx+rw)*w_f), int((ry+rh)*h_f)
            crop = screen[max(0,y1):min(h_f,y2), max(0,x1):min(w_f,x2)]
            crop = cv2.resize(crop, (crop.shape[1]*2, crop.shape[0]*2), interpolation=cv2.INTER_CUBIC)
            res = reader.readtext(crop, detail=1, allowlist='0123456789ID: ')
            nums = re.findall(r'\d+', ' '.join([r[1] for r in res]))
            for n in nums:
                if 6 <= len(n) <= 7:
                    with self.shared_data["lock"]:
                        self.shared_data["room_ids"][self.group_id] = n
                        self.shared_data["joined_counts"][self.group_id] = 1
                    self.log(f"==> OCR ID PHÒNG: [{n}]")
                    return True
            time.sleep(3)
        return False

    def wait_for_room_logic(self, step):
        start = time.time()
        while time.time() - start < step.get("timeout", 300) and self.running:
            with self.shared_data["lock"]:
                if self.shared_data.get("room_ids", {}).get(self.group_id): return True
            time.sleep(2)
        return False

    def input_room_id_logic(self):
        with self.shared_data["lock"]: rid = self.shared_data.get("room_ids", {}).get(self.group_id, "")
        if not rid: return False
        digit_imgs = {}
        for i in range(10):
            p = resource_path(f"images_boxphone/btn_{i}.png")
            if os.path.exists(p):
                img = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
                if img is not None: digit_imgs[str(i)] = img
        
        screen = self.get_screenshot()
        if screen is None: return False
        scale = screen.shape[0] / BASE_HEIGHT


        for digit in rid:
            if not self.running: return False
            t_img = digit_imgs.get(digit)
            if t_img is None: continue
            
            found = False
            for _ in range(3):
                scr = self.get_screenshot()
                if scr is None: continue
                scr_gray = cv2.cvtColor(scr, cv2.COLOR_BGR2GRAY)
                
                # Thử cả scale và native
                for curr_scale in [scale, 1.0]:
                    if abs(curr_scale - 1.0) < 0.001: t_s = t_img
                    else: t_s = cv2.resize(t_img, (int(t_img.shape[1]*curr_scale), int(t_img.shape[0]*curr_scale)), interpolation=cv2.INTER_AREA)
                    
                    if scr_gray.shape[0] < t_s.shape[0] or scr_gray.shape[1] < t_s.shape[1]:
                        continue
                        
                    res = cv2.matchTemplate(scr_gray, t_s, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, ml = cv2.minMaxLoc(res)
                    if mv >= 0.85:
                        self.call_adb(["shell", "input", "tap", str(ml[0]+t_s.shape[1]//2), str(ml[1]+t_s.shape[0]//2)])
                        found = True; break
                if found:
                    time.sleep(0.3)
                    break
                time.sleep(0.5)
        return True

    def notify_joined_logic(self):
        """Guest gọi sau khi đã vào phòng thành công để thông báo cho host biết."""
        with self.shared_data["lock"]:
            old = self.shared_data["joined_counts"].get(self.group_id, 0)
            self.shared_data["joined_counts"][self.group_id] = old + 1
        self.log(f"===> Đã thông báo vào phòng. Tổng: {self.shared_data['joined_counts'].get(self.group_id, 0)}")
        return True

    def wait_for_players_logic(self, step):
        target = step.get("count", 4) + 1
        start = time.time()
        while time.time() - start < step.get("timeout", 300) and self.running:
            with self.shared_data["lock"]: curr = self.shared_data["joined_counts"].get(self.group_id, 0)
            if curr >= target: return True
            self.update_status(f"Team {curr}/{target}"); time.sleep(2)
        self.log(f"!! wait_for_players timeout. Hiện tại: {self.shared_data['joined_counts'].get(self.group_id, 0)}/{target}")
        return False

    def buy_exp_logic(self, step):
        # Vật phẩm 1: 1 ngày x2
        self.log("Đang mua vật phẩm EXP 1 ngày...")
        if self.search_logic({"target": "images_boxphone/1ngay_x2.jpg", "timeout": 10}):
            self.click_image_logic({"target": "images_boxphone/1ngay_x2.jpg", "timeout": 5})
            self.click_image_logic({"target": "images_boxphone/100_ruby.jpg", "timeout": 10})
            self.click_image_logic({"target": "images_boxphone/buy_button.png", "timeout": 10})
            time.sleep(2)
            if self.search_logic({"target": "images_boxphone/chua_du_ruby.jpg", "timeout": 5}):
                self.log("!! KHÔNG ĐỦ RUBY - Bỏ qua.")
                self.press_esc_logic({"wait": 1})
                return True
            self.click_image_logic({"target": "images_boxphone/mo_button.png", "timeout": 10})
            time.sleep(1)

        # Vật phẩm 2: 4 ngày (tháng) x2
        self.log("Đang mua vật phẩm EXP 4 ngày...")
        if self.search_logic({"target1": "images_boxphone/4thang_x2.jpg", "target2": "images_boxphone/4thang_x2_1.jpg", "timeout": 10}):
            self.click_image_logic({"target": "images_boxphone/4thang_x2.jpg", "target1": "images_boxphone/4thang_x2_1.jpg", "timeout": 5})
            self.click_image_logic({"target1": "images_boxphone/100_ruby.jpg", "target2": "images_boxphone/60ruby.jpg", "timeout": 10})
            self.click_image_logic({"target": "images_boxphone/buy_button.png", "timeout": 10})
            time.sleep(2)
            if self.search_logic({"target": "images_boxphone/chua_du_ruby.jpg", "timeout": 5}):
                self.log("!! KHÔNG ĐỦ RUBY - Bỏ qua.")
                self.press_esc_logic({"wait": 2})
                return True
            self.click_image_logic({"target": "images_boxphone/mo_button.png", "timeout": 10})
        return True

    def sync_autowin_logic(self, step):
        start = time.time()
        with self.shared_data["lock"]:
            self.shared_data["autowin_barrier"][self.group_id] = self.shared_data["autowin_barrier"].get(self.group_id, 0) + 1
        while time.time() - start < 120 and self.running:
            with self.shared_data["lock"]:
                if self.shared_data["autowin_barrier"].get(self.group_id, 0) >= 5: break
            time.sleep(0.5)
        self.click_image_logic({"action": "click_image_if", "target1": "images_boxphone/autowin1.jpg", "target2": "images_boxphone/on_auto_win1.jpg", "timeout": 20, "confidence": 0.8})
        with self.shared_data["lock"]: self.shared_data["autowin_barrier"][self.group_id] = 0
        return True

    def run(self, accounts, modes, shared_data):
        self.accounts_list = accounts
        self.modes = modes
        self.group_id = self.device_index // 5
        self.shared_data = shared_data
        self.running = True
        
        # --- FULL SCRIPTS SYNCHRONIZED FROM LD VERSION ---
        
        # 1. GIAI ĐOẠN LOGIN (Đã được tối ưu cho BoxPhone)
        login_script = [
            {"action": "click_image_if", "target1": "images_boxphone/dangnhap_box.png","target2": "images_boxphone/dangnhap_box1.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target1": "images_boxphone/dangnhap_box.png","target2": "images_boxphone/dangnhap_box1.png", "timeout": 3, "confidence": 0.7},
            {"action": "input_account"},
            {"action": "click_image_if", "target1": "images_boxphone/matkhau.png",  "timeout": 10, "confidence": 0.7},
            {"action": "input_password"},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target1": "images_boxphone/xong.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target1": "images_boxphone/dangnhap2.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/okdangnhap.png", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/okdangnhap.png",  "timeout": 4, "confidence": 0.7},
            
            {"action": "click_image_if", "target": "images_boxphone/batdau.png", "timeout": 6, "confidence": 0.7},
            {"action": "click_image_if",  "target": "images_boxphone/dkysau.png","timeout": 10, "confidence": 0.7},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
        ]
        
        tutorial_script = [
            {
                "action": "cases",
                "timeout" : 120,
                "cases": [
                    {
                        "trigger": "images_boxphone/vaotran.png",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image_if", "target": "images_boxphone/vaotran.png", "timeout": 3, "confidence": 0.7},
                             {"action": "click_image_if", "target": "images_boxphone/vaotran.png", "timeout": 3, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images_boxphone/vaotran.png", "timeout": 3, "confidence": 0.7},
                            {"action": "wait", "timeout": 3},
                            {"action": "click_image_if", "target1": "images_boxphone/vaotran1.png", "target2": "images_boxphone/vao_tran_button_3.jpg", "target3": "images_boxphone/vao_tran_button_2.jpg","target4": "images_boxphone/vao_tran_box.png", "timeout": 30, "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images_boxphone/vaotran1.png", "target2": "images_boxphone/vao_tran_button_3.jpg", "target3": "images_boxphone/vao_tran_button_2.jpg","target4": "images_boxphone/vao_tran_box.png", "timeout": 4, "confidence": 0.7}
                        ]
                    },
                    {
                        "trigger": "images_boxphone/vao_button.png", 
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image_if", "target": "images_boxphone/vao_button.png", "timeout": 5, "confidence": 0.7},
                            {"action": "click_image", "target": "images_boxphone/logo1.png", "timeout": 20, "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images_boxphone/autowin.png", "target2":"images_boxphone/on_auto_win_1.jpg", "timeout": 20, "confidence": 0.75, "use_color": True},
                            {"action": "click_image", "target1": "images_boxphone/minimize.png", "target2":"images_boxphone/minimize1.jpg", "target3":"images_boxphone/minimize2.jpg", "target4":"images_boxphone/minimize3.jpg", "timeout": 20, "confidence": 0.7},
                            {"action": "click_image", "target1": "images_boxphone/victory.png", "timeout": 120, "confidence": 0.7},
                            {"action": "click_any", "wait": 12},
                            {"action": "click_any", "wait": 5},
                            
                        ]
                    },
                    {
                        "trigger": "images_boxphone/an_de_tro_lai.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image_if", "target": "images_boxphone/an_de_tro_lai.jpg", "confidence": 0.7},
                            {"action": "wait", "timeout": 2},
                            {"action": "click_image_if", "target": "images_boxphone/an_de_tro_lai.jpg", "confidence": 0.7},
                            {"action": "wait", "timeout": 2},
                            {"action": "click_image_if", "target": "images_boxphone/an_de_tro_lai.jpg", "confidence": 0.7},
                            {"action": "click_image_if", "target": "images_boxphone/x_start.jpg", "confidence": 0.7},
                            {"action": "click_image_if", "target": "images_boxphone/x_start1.jpg", "confidence": 0.7},
                            {"action": "click_image_if", "target": "images_boxphone/x_start1.jpg", "confidence": 0.7}
                        ]
                    },
                    {
                        "trigger": "images_boxphone/x_start.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image_if", "target": "images_boxphone/x_start.jpg", "confidence": 0.7},
                            {"action": "click_image_if", "target": "images_boxphone/x_start1.jpg", "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images_boxphone/x_start1.jpg", "confidence": 0.7},
                        ]
                    },
                    {
                        "trigger": "images_boxphone/pvp.png",
                        "confidence": 0.7,
                        "script": []
                    }
                ]
            },
            {"action": "press_esc", "wait": 3},
            
            
        
        
        # 2. GIAI ĐOẠN VƯỢT TÂN THỦ (Full chi tiết từ LD)
        
            {"action": "click_image", "target": "images_boxphone/tuychon.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/1v1.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/x.png", "timeout": 5, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/pve.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/logo.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/autowin.png", "target2": "images_boxphone/autowin1.jpg", "target3": "images_boxphone/on_auto_win.jpg", "timeout": 20, "confidence": 0.75, "use_color": True},
            {"action": "click_image", "target1": "images_boxphone/minimize.png", "target2": "images_boxphone/minimize1.jpg", "target3": "images_boxphone/minimize2.jpg", "target4": "images_boxphone/minimize3.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/sansang.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok1.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/sansang.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/tuong3.png",  "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/ok1.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/victory.png", "timeout": 120, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
            {"action": "click_image_if", "target": "images_boxphone/victory.png", "timeout": 20, "confidence": 0.7},
            
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images_boxphone/daulai.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/sansang.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok1.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/sansang.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/tuong3.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/ok1.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/victory.png", "timeout": 120, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
            {"action": "click_image_if", "target": "images_boxphone/victory.png", "timeout": 10, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images_boxphone/sanh.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images_boxphone/sukien.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/sukien.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/krixi.png", "target2": "images_boxphone/krixi_loi.png", "timeout": 10, "confidence": 0.7},
            {"action": "click_any", "wait": 2},
            {"action": "click_any", "wait": 2},
            
            {"action": "click_image_if", "target1": "images_boxphone/lam.png", "target2": "images_boxphone/lam_box.png", "timeout": 10, "confidence": 0.7},
            {"action": "press_esc", "wait": 2} ,
            
            
            
             {"action": "press_esc", "wait": 2} ,
            {"action": "click_image", "target": "images_boxphone/sukien.png", "timeout": 20, "confidence": 0.7},
            {"action": "press_esc", "wait": 2} ,
           {"action": "press_esc", "wait": 2} ,
            
           
           
            {"action": "click_image_if", "target": "images_boxphone/dau_hang_button.png", "timeout": 7, "confidence": 0.7},
            
            {"action": "press_esc", "wait": 2} ,
            {"action": "click_image", "target": "images_boxphone/event.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/qua_tan_thu.png", "target2": "images_boxphone/skttt.png", "target3": "images_boxphone/qua_tan_thu1.jpg","timeout": 10, "confidence": 0.8},
            {"action": "wait", "timeout": 5},
            {"action": "swipe", "x1": 0.2, "y1": 0.8, "x2": 0.2, "y2": 0.6, "duration": 600},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target1": "images_boxphone/sktt.jpg", "target2": "images_boxphone/sktt1.jpg", "target3": "images_boxphone/sktt2.jpg", "target4": "images_boxphone/sktt3.jpg", "target5": "images_boxphone/sktt4.jpg", "target6": "images_boxphone/sktt5.jpg", "target7": "images_boxphone/sktt6.jpg", "target8": "images_boxphone/sktt7.jpg", "target9": "images_boxphone/sktt8.jpg", "target10": "images_boxphone/sktt9.jpg", "target11": "images_boxphone/sktt10.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/nhan_ruby_button.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_any", "wait": 3},
            {"action": "click_image", "target1": "images_boxphone/thoat_sk.png","target2": "images_boxphone/quaylaisktt.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/tui_do_button.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/vat_pham.png", "target2": "images_boxphone/vat_pham1.png","target3": "images_boxphone/vat_pham2.png","target4": "images_boxphone/vat_pham3.png","target5": "images_boxphone/vat_pham4.png","timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/su_dung_button.png","target2": "images_boxphone/su_dung.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target1": "images_boxphone/ok.png","target2": "images_boxphone/ok1.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2}
        ]

        # 2.5 GIAI ĐOẠN MUA EXP
        mua_exp_script = [
            {"action": "click_image", "target": "images_boxphone/hop_thu.jpg", "timeout": 20, "confidence": 0.6},
            {"action": "click_image_if", "target": "images_boxphone/ok_ruby.jpg", "timeout": 7, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/he_thong.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/nhan_nhanh.jpg", "timeout": 7, "confidence": 0.7},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images_boxphone/shop.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/vat_pham_shop.png","target2": "images_boxphone/vatpham.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/shopruby.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "swipe", "x1": 0.5, "y1": 0.8, "x2": 0.5, "y2": 0.5, "duration": 600},
            {"action": "wait", "timeout": 2},
            {"action": "buy_exp"},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
        ]

        # 3. GIAI ĐOẠN DÍNH GAME
        dinh_game_script = [
            {"action": "click_image", "target": "images_boxphone/dauthuong.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/logo_box.png","target2": "images_boxphone/logo4.png","target3": "images_boxphone/logo1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images_boxphone/autooff_box.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target1": "images_boxphone/minimize_box.png","target2": "images_boxphone/minimize_box1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target1": "images_boxphone/ready.png","target2": "images_boxphone/sansang_box.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target1": "images_boxphone/sansang5v5.png", "target2": "images_boxphone/sansang.png","target3": "images_boxphone/sansang_box.png","timeout": 20, "confidence": 0.7},
            
            {"action": "click_image_if", "target": "images_boxphone/ok3.png", "timeout": 15, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target1": "images_boxphone/tuong1.png", "target2": "images_boxphone/tuong2.png", "target3": "images_boxphone/tuong3.png", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 10, "confidence": 0.7},
             {"action": "loop",
                "count": 4,
                "steps": [
                    {"action": "click_coords", "x": 903, "y": 945, "timeout": 2},
                    {"action": "wait", "timeout": 15}
                ]
                },
            {"action": "click_image", "target": "images_boxphone/victory.png", "timeout": 600, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2} ,
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images_boxphone/event_default.png", "timeout": 20, "confidence": 0.9},
            {"action": "press_esc", "wait": 2},
            {"action": "wait", "timeout": 5},
            {"action": "press_esc", "wait": 2} ,
        ]

        # 4. GIAI ĐOẠN GHÉP ĐỘI (TEAM UP)        
        teamup_host_script = [
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images_boxphone/team5.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/x1.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/x1.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 3, "confidence": 0.7},
            {"action": "get_room_id", "timeout": 30, "roi": [0.50, 0.0, 0.30, 0.10]},
            {"action": "wait_for_players", "count": 4, "timeout": 300},
            {"action": "click_image_if", "target": "images_boxphone/x1.png", "timeout": 5, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/da_ro.png", "timeout": 3, "confidence": 0.75},
            {"action": "click_image_if", "target": "images_boxphone/daro.png", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/pve.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/ready.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ready.png", "timeout": 2, "confidence": 0.7},
        ]
        
        teamup_guest_script = [
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images_boxphone/pvp.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/idphong.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait_for_room", "timeout": 300},
            {"action": "input_room_id"},
            {"action": "click_image", "target": "images_boxphone/vao.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/da_ro.png", "timeout": 300, "confidence": 0.7},
            # Thông báo cho host biết guest đã vào phòng thành công
            {"action": "notify_joined"},
        ]

        # 5. CÁC HÀNH ĐỘNG LẶP LẠI (SHARED BATTLE LOGIC)
        idx = (self.device_index % 5) + 1
        t1 = f"images_boxphone/tuong0{idx}.jpg"
        t2 = f"images_boxphone/tuong{idx+5:02d}.jpg" 
        
        shared_battle_script = [
            {"action": "click_image", "target1": "images_boxphone/logo1.png", "target2": "images_boxphone/logo_auto.jpg", "timeout": 50, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/autowin1.jpg", "target2": "images_boxphone/on_auto_win.jpg", "timeout": 3, "confidence": 0.75, "use_color": True},
            {"action": "click_image", "target1": "images_boxphone/minimize.png", "target2": "images_boxphone/minimize1.jpg", "target3": "images_boxphone/minimize2.jpg", "target4": "images_boxphone/minimize3.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images_boxphone/ready.png", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/san_sang.jpg", "timeout": 40, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok3.png", "timeout": 25, "confidence": 0.7},
            {"action": "click_image_if", "target1": t1, "target2": t2, "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 10},
            {"action": "click_image_if", "target1": "images_boxphone/logo.png", "target2": "images_boxphone/logo2.png", "timeout": 60, "confidence": 0.7},
            {"action": "wait", "timeout": 10},
            {
                "action": "loop",
                "count": 11,
                "steps": [
                    {"action": "click_coords", "x": 903, "y": 945, "timeout": 2},
                    {"action": "wait", "timeout": 15}
                ]
            },
            {"action": "wait", "timeout": 6},
            {"action": "sync_autowin", "timeout": 120},
            {"action": "click_image", "target1": "images_boxphone/minimize.png", "target2": "images_boxphone/minimize1.jpg", "target3": "images_boxphone/minimize2.jpg", "target4": "images_boxphone/minimize3.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/victory.png", "timeout": 600, "confidence": 0.7},
            {"action": "wait", "timeout": 10},
            {"action": "click_image_if", "target": "images_boxphone/victory.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 6},
            {"action": "click_image", "target": "images_boxphone/tiep_tuc1.png", "timeout": 120, "confidence": 0.7},
            {"action": "wait", "timeout": 6},
            {"action": "click_image", "target": "images_boxphone/tiep_tuc2.png", "timeout": 120, "confidence": 0.7},
            {"action": "click_any", "wait": 6},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 4, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 4, "confidence": 0.7},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images_boxphone/daulai.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 2, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 2, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images_boxphone/close.png", "timeout": 2, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image_if", "target": "images_boxphone/ok.png", "timeout": 2, "confidence": 0.7},
            {"action": "wait", "timeout": 3}
        ]

        # 6. GIAI ĐOẠN ĐĂNG XUẤT
        uplevel_script = [
            {"action": "click_image", "target": "images_boxphone/logo.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images_boxphone/autowin.png", "target2": "images_boxphone/autowin1.jpg", "target3": "images_boxphone/off_auto_win.jpg", "timeout": 20, "confidence": 0.75, "use_color": True},
            {"action": "click_image", "target1": "images_boxphone/minimize.png", "target2": "images_boxphone/minimize1.jpg", "target3": "images_boxphone/minimize2.jpg", "target4": "images_boxphone/minimize3.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/home.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/cai_dat_button.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/logout.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images_boxphone/ok.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
        ]
        
        # --- ASSEMBLE SCRIPT BASED ON MODES ---
        self.script = []
        if self.modes.get("login"): self.script += login_script
        if self.modes.get("tutorial"): self.script += tutorial_script
        if self.modes.get("mua_exp"): self.script += mua_exp_script
        if self.modes.get("dinh_game"): self.script += dinh_game_script
        if self.modes.get("teamup"):
            if self.is_host:
                # Host: wait_for_players đã có sẵn trong teamup_host_script
                self.script += teamup_host_script
            else:
                # Guest: vào phòng → notify_joined (đã có trong script) → chờ host bắt đầu
                self.script += teamup_guest_script
                self.script.append({"action": "wait_for_players", "count": 4, "timeout": 300})
            
            battle_loop = {
                "action": "loop", 
                "count": self.modes.get("battle_count", 2), 
                "steps": shared_battle_script
            }
            self.script.append(battle_loop)
        
        self.script += uplevel_script # ALWAYS LOGOUT AT END

        while self.running:
            self.current_account = None
            with FILE_LOCK:
                for acc in self.accounts_list:
                    if not acc.get("used"):
                        acc["used"] = True; self.current_account = acc
                        self.update_ui_func(); break
            if not self.current_account: break
            self.log(f">> START: {self.current_account['tk']}")
            
            # Host reset dữ liệu nhóm khi bắt đầu acc mới
            if self.is_host:
                with self.shared_data["lock"]:
                    if self.group_id in self.shared_data["room_ids"]:
                        del self.shared_data["room_ids"][self.group_id]
                    self.shared_data["joined_counts"][self.group_id] = 0
            
            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step):
                    success = False; break
            
            if self.running:
                self.report_stats_func(success, self.current_account)
                self.accounts_processed += 1
            gc.collect()
        self.update_status("Xong"); self.running = False

class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvLQTool(BoxPhone)")
        self.geometry("1000x650")
        self.configure(fg_color=BG_COLOR)
        self.accounts_data = []
        self.account_file_path = None
        self.instances = []
        self.active_workers = []
        self.success_count = 0
        self.failure_count = 0
        self.shared_data = {"room_ids": {}, "joined_counts": {}, "autowin_barrier": {}, "lock": threading.Lock()}
        self.adb_path = self.find_adb()
        self.device_map = {}
        self.device_cards = {}
        
        try:
            self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(64, 64))
            self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
            self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))
        except:
            self.logo_img = self.start_icon = self.stop_icon = None
        
        self.setup_layout()
        self.scan_devices()
        
        # Redirect stdout và stderr về log UI
        sys.stdout = StdoutRedirector(self.add_log)
        sys.stderr = StdoutRedirector(self.add_log)
        
        threading.Thread(target=init_ocr_reader, args=(self.add_log,), daemon=True).start()


    def setup_layout(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=NAV_COLOR); self.sidebar.pack(side="left", fill="y")
        if self.logo_img: ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=20)
        ctk.CTkLabel(self.sidebar, text="BOXPHONE EDITION", font=("Arial", 16, "bold"), text_color=ACCENT_GREEN).pack()
        
        self.account_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR); self.account_card.pack(padx=20, pady=20, fill="x")
        ctk.CTkButton(self.account_card, text="NẠP FILE ACC", command=self.load_accounts, fg_color="#EAB308", text_color="#000").pack(pady=10, padx=10, fill="x")

        # ADB Config
        self.adb_config_frame = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR); self.adb_config_frame.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.adb_config_frame, text="ADB PATH", font=("Arial", 10, "bold")).pack(pady=(5,0))
        self.adb_path_entry = ctk.CTkEntry(self.adb_config_frame, height=28, placeholder_text="adb")
        self.adb_path_entry.pack(padx=10, pady=5, fill="x")
        self.adb_path_entry.insert(0, self.adb_path)
        ctk.CTkButton(self.adb_config_frame, text="Lưu & Refresh", command=self.save_adb_and_refresh, height=24).pack(padx=10, pady=(0,5), fill="x")

        self.btn_start = ctk.CTkButton(self.sidebar, text=" CHẠY TẤT CẢ", image=self.start_icon, compound="left", command=self.start_all, height=45, font=("Arial", 14, "bold"), fg_color="#10b981", hover_color="#059669")
        self.btn_start.pack(side="bottom", padx=20, pady=(10, 20), fill="x")
        self.btn_stop = ctk.CTkButton(self.sidebar, text=" DỪNG TẤT CẢ", image=self.stop_icon, compound="left", command=self.stop_all, fg_color="#4b5563", hover_color="#374151", height=40)
        self.btn_stop.pack(side="bottom", padx=20, pady=0, fill="x")


        # Main Area
        self.main_content = ctk.CTkFrame(self, fg_color="transparent"); self.main_content.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        
        # Device List
        inst_header = ctk.CTkFrame(self.main_content, fg_color="transparent"); inst_header.pack(fill="x")
        ctk.CTkLabel(inst_header, text="DANH SÁCH BOXPHONE", font=("Arial", 14, "bold"), text_color=ACCENT_GREEN).pack(side="left")
        self.btn_refresh = ctk.CTkButton(inst_header, text="Làm Mới", command=self.scan_devices, width=80)
        self.btn_refresh.pack(side="right")
        
        self.device_list_frame = ctk.CTkScrollableFrame(self.main_content, height=200, fg_color=CARD_COLOR); self.device_list_frame.pack(fill="x", pady=10)
        
        # Modes
        mode_label = ctk.CTkLabel(self.main_content, text="CHẾ ĐỘ HOẠT ĐỘNG", font=("Arial", 12, "bold"), text_color="#888")
        mode_label.pack(pady=(10, 5))
        
        self.mode_frame = ctk.CTkFrame(self.main_content, fg_color=CARD_COLOR)
        self.mode_frame.pack(fill="x", pady=5, padx=5)
        self.mode_frame.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.mode_login = ctk.CTkCheckBox(self.mode_frame, text="LOGIN"); self.mode_login.grid(row=0, column=0, pady=10); self.mode_login.select()
        self.mode_tutorial = ctk.CTkCheckBox(self.mode_frame, text="TÂN THỦ"); self.mode_tutorial.grid(row=0, column=1); self.mode_tutorial.select()
        self.mode_mua_exp = ctk.CTkCheckBox(self.mode_frame, text="MUA EXP"); self.mode_mua_exp.grid(row=0, column=2); self.mode_mua_exp.select()
        self.mode_dinh_game = ctk.CTkCheckBox(self.mode_frame, text="DÍNH GAME"); self.mode_dinh_game.grid(row=0, column=3); self.mode_dinh_game.select()
        self.mode_teamup = ctk.CTkCheckBox(self.mode_frame, text="GHÉP ĐỘI"); self.mode_teamup.grid(row=0, column=4); self.mode_teamup.select()
        
        self.battle_count_entry = ctk.CTkEntry(self.main_content, width=80, placeholder_text="Số trận Battle (2)")
        self.battle_count_entry.pack(pady=5); self.battle_count_entry.insert(0, "2")

        # Stats
        self.stats_inner = ctk.CTkFrame(self.main_content, fg_color="transparent"); self.stats_inner.pack(fill="x", pady=10)
        self.success_val = ctk.CTkLabel(self.stats_inner, text="0", font=("Arial", 50, "bold"), text_color="#4ADE80"); self.success_val.pack()
        ctk.CTkLabel(self.stats_inner, text="TÀI KHOẢN THÀNH CÔNG", font=("Arial", 14)).pack()
        
        # Log Window
        ctk.CTkLabel(self.main_content, text="LOG HỆ THỐNG", font=("Arial", 12, "bold"), text_color="#888").pack(pady=(10,0))
        self.log_txt = ctk.CTkTextbox(self.main_content, height=150, fg_color="#18181b", text_color="#d1d5db", font=("Consolas", 11))
        self.log_txt.pack(fill="both", expand=True, pady=10)
        self.load_adb_config()

    def find_adb(self):
        # Ưu tiên adb đi kèm tool
        local_adb = resource_path("adb.exe")
        paths = [local_adb, "adb", r"C:\LDPlayer\LDPlayer9\adb.exe"]
        for p in paths:
            try:
                if p == "adb" or os.path.exists(p):
                    subprocess.run([p, "version"], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                    return p
            except: continue
        return "adb"

    def save_adb_and_refresh(self):
        path = self.adb_path_entry.get().strip()
        if not path:
            self.adb_path = "adb"
        else:
            # Nếu người dùng chỉ dán đường dẫn thư mục, tự động thêm \adb.exe
            if os.path.isdir(path):
                path = os.path.join(path, "adb.exe")
            
            if os.path.exists(path) or path == "adb":
                self.adb_path = path
            else:
                self.add_log(f"LỖI: Không tìm thấy file adb tại {path}")
                return

        try:
            with open("adb_config.txt", "w") as f: f.write(self.adb_path)
            self.adb_path_entry.delete(0, 'end')
            self.adb_path_entry.insert(0, self.adb_path)
        except: pass
        
        self.add_log(f"Đã cập nhật ADB: {self.adb_path}")
        self.scan_devices()

    def load_adb_config(self):
        if os.path.exists("adb_config.txt"):
            try:
                with open("adb_config.txt", "r") as f:
                    path = f.read().strip()
                    if path:
                        self.adb_path = path
                        self.adb_path_entry.delete(0, 'end')
                        self.adb_path_entry.insert(0, self.adb_path)
            except: pass

    def scan_devices(self):
        self.btn_refresh.configure(state="disabled", text="Đang quét...")
        threading.Thread(target=self._scan_devices_thread, daemon=True).start()

    def _scan_devices_thread(self):
        self.device_map = {}
        serials = []
        try:
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            serials = [l.split('\t')[0] for l in res.stdout.strip().split('\n')[1:] if "device" in l]
            # Sắp xếp theo số máy trích xuất được
            serials.sort(key=lambda s: extract_device_number(s) or 0)
        except Exception as e:
            print(f"Lỗi quét ADB: {e}")

        # Update UI in main thread
        self.after(0, lambda: self._update_device_list_ui(serials))

    def _update_device_list_ui(self, serials):
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        # Nhóm các serial theo thứ tự hiển thị (mỗi nhóm 5 máy thành 1 team)
        teams_dict = {}
        for idx, s in enumerate(serials):
            team_id = (idx // 5) + 1
            if team_id not in teams_dict:
                teams_dict[team_id] = []
            teams_dict[team_id].append(s)
        
        # Sắp xếp các Team theo thứ tự
        sorted_team_ids = sorted(teams_dict.keys())
        
        for team_num in sorted_team_ids:
            team_serials = teams_dict[team_num]
            
            team_card = ctk.CTkFrame(self.device_list_frame, fg_color="#1a1a1a", corner_radius=8, border_width=1, border_color="#333")
            team_card.pack(fill="x", pady=4, padx=10)
            
            # --- Team Header & Controls ---
            header = ctk.CTkFrame(team_card, fg_color="transparent", height=40)
            header.pack(fill="x", padx=10, pady=5)
            
            ctk.CTkLabel(header, text=f"TEAM {team_num}", font=("Arial", 14, "bold"), text_color=ACCENT_GREEN).pack(side="left")
            
            # Team Controls
            btn_play_all = ctk.CTkButton(header, text="START TEAM", image=self.start_icon, width=110, height=30, fg_color="#10b981", font=("Arial", 11, "bold"), command=lambda ts=team_serials: self.start_team(ts))
            btn_play_all.pack(side="right", padx=5)
            
            btn_stop_all = ctk.CTkButton(header, text="STOP TEAM", image=self.stop_icon, width=110, height=30, fg_color="#4b5563", font=("Arial", 11, "bold"), command=lambda ts=team_serials: self.stop_team(ts))
            btn_stop_all.pack(side="right", padx=5)

            # --- Team Device Grid ---
            device_grid = ctk.CTkFrame(team_card, fg_color="transparent")
            device_grid.pack(fill="x", padx=10, pady=(0, 5))
            
            for idx_in_team, s in enumerate(team_serials):
                dev_num = extract_device_number(s)
                # global_idx là chỉ số trong danh sách serials đã sắp xếp để đồng bộ group_id = idx // 5
                global_idx = serials.index(s)
                display_num = dev_num if dev_num is not None else (global_idx + 1)
                
                is_host = (idx_in_team == 0)
                self.device_map[s] = {"idx": global_idx, "is_host": is_host, "display_num": display_num, "team_num": team_num}
                
                # Ô thiết bị nhỏ gọn
                dev_box = ctk.CTkFrame(device_grid, fg_color="#252525", corner_radius=4, width=150, height=50)
                dev_box.pack(side="left", padx=2, fill="y", expand=True)
                dev_box.pack_propagate(False)
                
                # Role & Number
                role_color = "#3b82f6" if is_host else "#888"
                lbl_name = ctk.CTkLabel(dev_box, text=f"MÁY {display_num}", font=("Arial", 11, "bold"), text_color=role_color)
                lbl_name.pack(pady=(2, 0))
                
                # Status (Gọn hơn)
                status_lbl = ctk.CTkLabel(dev_box, text="Sẵn sàng", font=("Arial", 10), text_color="#666")
                status_lbl.pack(pady=(0, 2))
                
                self.device_cards[s] = {"status": status_lbl}

        self.btn_refresh.configure(state="normal", text="Làm Mới")
        if not serials:
            ctk.CTkLabel(self.device_list_frame, text="Không tìm thấy thiết bị nào.", text_color="#888").pack(pady=20)

    def start_team(self, serials):
        for s in serials: self.start_single_device(s)

    def stop_team(self, serials):
        for s in serials: self.stop_single_device(s)


    def load_accounts(self):
        p = fd.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not p: return
        self.account_file_path = p
        self.accounts_data = []
        with open(p, 'r', encoding='utf-8') as f:
            for l in f:
                parts = l.strip().split('|', 1)
                if len(parts)>=2: self.accounts_data.append({"tk":parts[0], "mk":parts[1], "used":False})
        self.add_log(f"Đã nạp {len(self.accounts_data)} acc.")

    def start_all(self):
        if not self.accounts_data: 
            self.add_log("Vui lòng nạp file tài khoản trước.")
            return
        for s in self.device_map:
            self.start_single_device(s)

    def stop_all(self):
        for w in self.active_workers[:]:
            w.running = False
            self.active_workers.remove(w)
        for s in self.device_cards:
            self.device_cards[s]["status"].configure(text="Stopping...", text_color="#888")

    def start_single_device(self, serial):
        # Prevent duplicate workers for same device
        for w in self.active_workers:
            if w.device_id == serial and w.running:
                return

        b_count = 2
        try: b_count = int(self.battle_count_entry.get().strip())
        except: pass
        modes = {"login":self.mode_login.get(), "tutorial":self.mode_tutorial.get(), "mua_exp":self.mode_mua_exp.get(), "dinh_game":self.mode_dinh_game.get(), "teamup":self.mode_teamup.get(), "battle_count":b_count}
        
        def update_single_status():
             # Find status label for this serial
             if serial in self.device_cards:
                 for w in self.active_workers:
                     if w.device_id == serial:
                         self.device_cards[serial]["status"].configure(text=w.status, text_color="#4ADE80" if not w.is_lagging else "#FB7185")
                         break
             self.update_all_ui()

        dev_info = self.device_map[serial]
        worker = AutoClickerInstance(serial, dev_info["idx"], dev_info["is_host"], self.adb_path, self.add_log, update_single_status, self.report_stats)
        self.active_workers.append(worker)
        threading.Thread(target=worker.run, args=(self.accounts_data, modes, self.shared_data), daemon=True).start()
        self.add_log(f"Bắt đầu: {serial} (Máy {dev_info['display_num']}, Team {dev_info['team_num']}, {'HOST' if dev_info['is_host'] else 'GUEST'})")

    def stop_single_device(self, serial):
        for w in self.active_workers[:]:
            if w.device_id == serial:
                w.running = False
                self.active_workers.remove(w)
        if serial in self.device_cards:
            self.device_cards[serial]["status"].configure(text="Stopped", text_color="#888")


    def report_stats(self, success, account):
        if success: self.success_count += 1
        else: self.failure_count += 1
        if account:
            fn = "SUCCESS_ACC.txt" if success else "FAILED_ACC.txt"
            with FILE_LOCK:
                with open(fn, "a") as f: f.write(f"{account['tk']}|{account['mk']}\n")
                if self.account_file_path:
                    with open(self.account_file_path, "r") as f: lines = f.readlines()
                    with open(self.account_file_path, "w") as f:
                        for l in lines:
                            if l.strip() != f"{account['tk']}|{account['mk']}": f.write(l)
        self.after(0, self.update_all_ui)

    def update_all_ui(self):
        self.success_val.configure(text=str(self.success_count))

    def add_log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        full_text = f"[{now}] {text}"
        # print(full_text) # Bỏ print trực tiếp ở đây để tránh lặp vô tận khi đã redirect stdout
        try:
            self.after(0, lambda: self._safe_append_log(full_text))
        except:
            pass

    def _safe_append_log(self, msg):
        try:
            self.log_txt.insert("end", msg + "\n")
            self.log_txt.see("end")
        except:
            pass

# --- License Logic ---
def get_hwid():
    try:
        def get_cmd(cmd):
            try:
                res = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
                lines = [l.strip() for l in res.split('\n') if l.strip()]
                if len(lines) > 1:
                    val = lines[1].strip()
                    trash = ["filled", "default", "none", "00000000", "ffffffff", "unknown", "to be"]
                    if any(t in val.lower() for t in trash): return ""
                    return val
                return ""
            except: return ""

        hw_uuid = get_cmd("wmic csproduct get uuid")
        disk_serial = get_cmd("wmic diskdrive where 'index=0' get serialnumber")
        cpu_id = get_cmd("wmic cpu get processorid")
        board_serial = get_cmd("wmic baseboard get serialnumber")
        
        machine_guid = ""
        try:
            registry_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            machine_guid, _ = winreg.QueryValueEx(registry_key, "MachineGuid")
            winreg.CloseKey(registry_key)
        except: pass

        mac = str(uuid.getnode())
        combined = f"U:{hw_uuid}|D:{disk_serial}|C:{cpu_id}|B:{board_serial}|G:{machine_guid}|M:{mac}"
        return hashlib.sha256(combined.encode()).hexdigest()[:20].upper()
    except:
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:20].upper()

def verify_license(key, hwid):
    try:
        decoded = base64.b64decode(key).decode()
        expiry_str, signature = decoded.split('|')
        expected_sig = hashlib.sha256(f"{expiry_str}{hwid}{SECRET_KEY}".encode()).hexdigest()[:10]
        if signature != expected_sig: return False, "Key không hợp lệ cho máy này!"
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_date: return False, f"Key đã hết hạn vào {expiry_str}!"
        return True, expiry_str
    except:
        return False, "Key sai định dạng!"

class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KÍCH HOẠT MegaUpLvLQTool(BoxPhone)")
        self.geometry("500x550")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        self.hwid = get_hwid()
        self.setup_ui()

    def setup_ui(self):
        ctk.CTkLabel(self, text="MegaUpLvLQTool(BoxPhone)", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(40, 10))
        ctk.CTkLabel(self, text="HỆ THỐNG QUẢN LÝ BẢN QUYỀN", font=ctk.CTkFont(size=12)).pack(pady=(0, 30))
        hwid_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10); hwid_frame.pack(padx=40, fill="x")
        ctk.CTkLabel(hwid_frame, text="MÃ MÁY CỦA BẠN (HWID):", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10, 0))
        self.hwid_entry = ctk.CTkEntry(hwid_frame, placeholder_text=self.hwid, height=35, font=ctk.CTkFont(size=12))
        self.hwid_entry.insert(0, self.hwid); self.hwid_entry.configure(state="readonly"); self.hwid_entry.pack(padx=20, pady=(5, 10), fill="x")
        ctk.CTkLabel(self, text="Hãy gửi mã trên cho Admin để nhận Key kích hoạt.", font=ctk.CTkFont(size=10), text_color="#888").pack(pady=5)
        self.key_input = ctk.CTkEntry(self, placeholder_text="Nhập Key kích hoạt tại đây...", height=40)
        self.key_input.pack(padx=40, pady=20, fill="x")
        self.btn_activate = ctk.CTkButton(self, text="KÍCH HOẠT NGAY", command=self.activate, height=45, corner_radius=10, font=ctk.CTkFont(weight="bold"))
        self.btn_activate.pack(padx=40, pady=5, fill="x")
        self.status_label = ctk.CTkLabel(self, text="", text_color=ACCENT_RED); self.status_label.pack(pady=10)
        ctk.CTkLabel(self, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=12, weight="bold"), text_color="#777").pack(pady=(30, 20))

    def activate(self):
        key = self.key_input.get().strip()
        if not key: self.status_label.configure(text="Vui lòng nhập Key!"); return
        valid, msg = verify_license(key, self.hwid)
        if valid:
            with open(LICENSE_FILE, "w") as f: f.write(key)
            self.status_label.configure(text=f"Kích hoạt thành công! Hạn dùng: {msg}", text_color="#4ADE80")
            self.after(1500, self.launch_main)
        else: self.status_label.configure(text=msg, text_color=ACCENT_RED)

    def launch_main(self):
        self.destroy(); app = MultiPremiumApp(); app.mainloop()

if __name__ == "__main__":
    hwid = get_hwid()
    need_login = True
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            saved_key = f.read().strip()
        if saved_key:
            valid, _ = verify_license(saved_key, hwid)
            if valid: need_login = False
    
    if need_login:
        login = LoginApp()
        login.mainloop()
    else:
        app = MultiPremiumApp()
        app.mainloop()

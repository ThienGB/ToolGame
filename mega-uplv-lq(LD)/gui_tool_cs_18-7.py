# -*- coding: utf-8 -*-
import unicodedata
# import easyocr

# # Khởi tạo một biến toàn cục dùng chung cho tất cả các luồng thiết bị
# GLOBAL_OCR_READER = None

# import unicodedata
# import easyocr

# # Khởi tạo một biến toàn cục dùng chung cho tất cả các luồng thiết bị
# GLOBAL_OCR_READER = None

# def init_ocr_reader(log_func=None):
#     """Khởi tạo hoặc trả về bộ đọc EasyOCR dùng chung để tiết kiệm RAM"""
#     global GLOBAL_OCR_READER
#     if GLOBAL_OCR_READER is None:
#         if log_func:
#             log_func("[OCR] Đang tải mô hình ngôn ngữ EasyOCR (Tiếng Việt + Tiếng Anh)...")
#         try:
#             # Khởi tạo hỗ trợ tiếng Việt ('vi') và tiếng Anh ('en')
#             GLOBAL_OCR_READER = easyocr.Reader([ 'en'], gpu=False) # Đổi gpu=True nếu máy bạn có card Nvidia rời
#             if log_func:
#                 log_func("[OCR] Tải mô hình OCR (EasyOCR) thành công!")
#         except Exception as e:
#             if log_func:
#                 log_func(f"[OCR] LỖI khởi tạo EasyOCR: {e}")
#     return GLOBAL_OCR_READER


import base64
import gc
import hashlib
import json
import os
import random
import re
import shlex
import ssl
import string
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import winreg
from datetime import datetime

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

# Ensure console output uses UTF-8
try:
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
except: pass

import tkinter.filedialog as fd
import os
import time
from PIL import Image

try:
    import pytesseract
    # Try common Windows install locations so OCR works even if PATH is not set.
    if os.name == "nt":
        for candidate in [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                break
except Exception as e:
    pytesseract = None
    print(f"[OCR] Không thể import pytesseract: {e}")

def wait_until_text(self, device_id, roi):

    init_ocr_reader()

    while True:

        screen = self.get_screenshot(device_id)

        if screen is None:
            continue

        crop = self.crop_region(screen, *roi)

        results = self.ocr_read_text_with_boxes(crop)

        if results:
            return True

        time.sleep(0.03)
def quet_chu_vung(x1, y1, x2, y2, delay=1.0):
    """
    Hàm tự động chụp màn hình Boxphone, cắt vùng và đọc văn bản.
    delay: thời gian chờ (giây) để màn hình Boxphone kịp cập nhật sau hành động trước đó.
    """
    if pytesseract is None:
        print("[OCR] pytesseract chưa sẵn sàng, hãy cài đặt thư viện và Tesseract OCR.")
        return ""

    time.sleep(delay) # Chờ màn hình ổn định sau hành động trước
    
    # 1. Chụp và tải ảnh về máy
    os.system("adb shell screencap -p /sdcard/scan.png && adb pull /sdcard/scan.png .")
    
    # 2. Mở ảnh, cắt vùng và nhận diện chữ tiếng Việt
    try:
        img = Image.open("scan.png")
        vung_cat = img.crop((x1, y1, x2, y2))
        van_ban = pytesseract.image_to_string(vung_cat, lang="vie").strip()
        return van_ban
    except Exception as e:
        print(f"Lỗi khi đọc hình ảnh: {e}")
        return ""

# Ví dụ OCR bên dưới đã bị tắt để không chạy tự động khi import file.
# Nếu cần test thủ công, hãy gọi hàm quet_chu_vung(...) từ console.

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

BASE_WIDTH = 960.0
BASE_HEIGHT = 540.0

# --- Global Cache for Performance ---
GLOBAL_TEMPLATES = {}
TEMPLATE_LOCK = threading.Lock()

def get_cached_template(t_path, use_color=False):
    key = (t_path, use_color)
    with TEMPLATE_LOCK:
        if key in GLOBAL_TEMPLATES:
            return GLOBAL_TEMPLATES[key]
        
        real_path = resource_path(t_path)
        if os.path.exists(real_path):
            read_mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
            img = cv2.imread(real_path, read_mode)
            if img is not None:
                GLOBAL_TEMPLATES[key] = img
                return img
    return None

class AutoClickerInstance:
    #
    def __init__(self, device_id, adb_path, log_func, update_ui_func, report_stats_func):
        self.device_id = device_id
        self.adb_path = adb_path
        self.log_func = log_func
        self.update_ui_func = update_ui_func
        self.report_stats_func = report_stats_func
        self.running = False
        self.status = "Đang chờ"
        self.last_step_time = time.time()
        self.is_lagging = False
        self.current_account = None
        self.accounts_processed = 0
        self.last_captured_code = ""
        self.partner_code = ""
        self.skip_login_for_this_acc = False
        self.skip_all_retries = False
        self.use_external_codes = False
        self.code_entered = False
        self._loop_success_stack = []

    def log(self, msg, force_ui=False):
        # In trực tiếp ra console hệ thống (sys.__stdout__) để không bị Redirector đẩy lên UI
        try:
            sys.__stdout__.write(f"[{self.device_id}] {msg}\n")
            sys.__stdout__.flush()
        except: pass
        
        # Chỉ hiển thị lên UI nếu chứa các tiền tố thông báo quan trọng và KHÔNG phải là action hoặc timeout
        allowed_prefixes = [
            ">> START", 
            "[THÀNH CÔNG]",
            "[THẤT BẠI]"
        ]
        
        # Chặn tuyệt đối nếu là log action (chứa ==> hoặc ->) hoặc log Timeout không quan trọng
        is_action = "==>" in msg or "->" in msg
        is_timeout = "Timeout" in msg and "SAI PASS" not in msg and "BẢO TRÌ" not in msg
        
        is_allowed = any(prefix in msg for prefix in allowed_prefixes) or ("!!" in msg and not is_timeout)
        
        if force_ui or (is_allowed and not is_action and not is_timeout):
            self.log_func(f"[{self.device_id}] {msg}")

    def update_status(self, status, is_lagging=False):
        self.status = status
        self.is_lagging = is_lagging
        self.update_ui_func()

    def input_text_robust(self, text):
        if not text: return
        parts = text.split(' ')
        for i, part in enumerate(parts):
            if part:
                quoted = shlex.quote(part)
                cmd = [self.adb_path, "-s", self.device_id, "shell", f"input text {quoted}"]
                try:
                    subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                except: pass
                time.sleep(0.1)
            if i < len(parts) - 1:
                self.call_adb(["shell", "input", "text", "%s"])

    def escape_adb_text(self, text):
        if not text: return ""
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

    def call_adb(self, args, timeout=None):
        if timeout is None: timeout = 30
        cmd = [self.adb_path, "-s", self.device_id] + args
        try:
            return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        except subprocess.TimeoutExpired:
            self.log(f"!! ADB TIMEOUT ({timeout}s): {' '.join(args)}")
            return subprocess.CompletedProcess(cmd, 1, b'', b'')
    def execute_step(self, step):
        if not self.running: return False
        action = step.get("action")
        target_info = step.get("target") or step.get("target1", "")
        # self.log(f"==> Bước: {action} {f'({target_info})' if target_info else ''}") # Tắt log bước chạy chi tiết trên UI
        self.last_step_time = time.time()
        res = True
    # def force_stop_game(self):
    #     self.log("-> Đang thực hiện đóng ứng dụng triệt để...")
    #     # 1. Nhấn Home để thoát về launcher trước
    #     self.call_adb(["shell", "input", "keyevent", "3"])
    #     time.sleep(1)
    #     # 2. Force stop các package liên quan
    #     potential_apps = ["com.garena.game.kgvn64x", "com.garena.game.kgvn", "com.garena.game.kgtw"]
    #     for app in potential_apps:
        #     self.call_adb(["shell", "am", "force-stop", app])
        #     self.call_adb(["shell", "pkill", "-f", app])
        # time.sleep(2)

    #   def get_screenshot(self):
    #     # Thêm jitter ngẫu nhiên để tránh nghẽn ADB khi chạy quá nhiều tab cùng lúc
    #     time.sleep(random.uniform(0.1, 0.3))
    #     try:
    #         cmd = [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"]
    #         try:
    #             process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
    #             if process.returncode != 0: raise Exception("Lỗi exec-out")
    #             image_bytes = process.stdout
    #         except:
    #             cmd_fallback = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
    #             process = subprocess.run(cmd_fallback, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
    #             image_bytes = process.stdout.replace(b"\r\n", b"\n")

    #         if not image_bytes: return None
    #         image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    #         img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    #         return img
    #     except Exception as e:
    #         self.log(f"LỖI Chụp màn hình: {str(e)}")
    #         return None
            
    # def get_clipboard(self):
    #     """Đọc clipboard bằng cách ép buộc App Clipper lên Foreground để sync (Fix Android 10+)."""
    #     pkg = "com.example.clipper"
    #     path_in_android = f"/sdcard/Android/data/{pkg}/files/clip.txt"
        
    #     # 1. Ép buộc mở App Clipper lên (Dùng monkey cho chắc chắn 100%)
    #     self.log("[CLIPBOARD] Đang đồng bộ...")
    #     self.call_adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
    #     time.sleep(1.5) # Đợi app hiện lên, sync và tự ẩn mình
        
    #     # 2. Đọc file kết quả
    #     cmd = [self.adb_path, "-s", self.device_id, "shell", f"cat {path_in_android} 2>/dev/null"]
    #     try:
    #         res = subprocess.run(cmd, capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    #     except subprocess.TimeoutExpired:
    #         self.log("!! [CLIPBOARD] Timeout khi đọc clipboard.")
    #         return ""
        
    #     if not res.stdout: 
    #         self.log("!! [CLIPBOARD] File trống hoặc chưa có mã.")
    #         return ""
        
    #     try:
    #         raw_output = res.stdout.decode('utf-8', errors='ignore').strip()
    #     except:
    #         return ""

    #     if not raw_output: return ""
        
    #     lines = raw_output.split('\n')
    #     clean_lines = [l.strip() for l in lines if l.strip() and "adb" not in l.lower() and "*" not in l]
        
    #     if clean_lines:
    #         content = clean_lines[-1]
            
    #         # --- LỌC LẤY MÃ MỜI GIỮA HAI DẤU GẠCH NGANG -- ---
    #         import re
    #         match = re.search(r'--([A-Za-z0-9]+)--', content)
    #         if match:
    #             content = match.group(1)
    #             self.log(f"==> [CLIPBOARD] Đã lọc mã mời: {content}")
    #         else:
    #             self.log(f"==> [CLIPBOARD] Lấy mã thành công (Raw): {content}")
            
    #         return content
        
    #     return ""
        # # service call clipboard 2 i32 1 (lấy dữ liệu clipboard)
        #     try:
        #         cmd_service = [self.adb_path, "-s", self.device_id, "shell", "service call clipboard 2 i32 1"]
        #         res_service = subprocess.run(cmd_service, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
        #         # Kết quả service call cần parse rất phức tạp (HEX), nên đây chỉ là phương án dự phòng
        #     except: pass

        #     # 3. Thất bại
        #     return ""


    # def quet_chu_vung(self, x1, y1, x2, y2, delay=1.0):
    #     # """
    #     # Hàm tự động chụp màn hình Boxphone, cắt vùng và đọc văn bản.
    #     # Hoạt động độc lập và an toàn cho từng luồng thiết bị.
    #     # """
    #     time.sleep(delay)  # Chờ màn hình ổn định sau hành động trước đó
        
    #     # Tạo tên file ảnh riêng biệt cho từng thiết bị để tránh ghi đè dữ liệu khi chạy đa luồng
    #     local_filename = f"scan_{self.device_id.replace(':', '_')}.png"
    #     remote_path = f"/sdcard/scan_{self.device_id.replace(':', '_')}.png"
        
    #     # 1. Chụp và tải ảnh về máy tính qua ADB của luồng hiện tại
    #     self.call_adb(["shell", "screencap", "-p", remote_path])
    #     self.call_adb(["pull", remote_path, local_filename])
        
    #     # 2. Mở ảnh, cắt vùng và nhận diện chữ tiếng Việt
    #     try:
    #         if pytesseract is None:
    #             self.log("Lỗi OCR: pytesseract chưa sẵn sàng")
    #             return ""
    #         if os.path.exists(local_filename):
    #             img = Image.open(local_filename)
    #             vung_cat = img.crop((x1, y1, x2, y2))
    #             van_ban = pytesseract.image_to_string(vung_cat, lang="vie").strip()
                
    #             # Dọn dẹp file ảnh sau khi quét xong để tránh nặng máy
    #             try:
    #                 os.remove(local_filename)
    #                 self.call_adb(["shell", "rm", remote_path])
    #             except: pass
                
    #             return van_ban
    #         else:
    #             return ""
    #     except Exception as e:
    #         self.log(f"Lỗi khi đọc hình ảnh OCR: {str(e)}")
    #         return ""
    
        
        if action == "click_image":
            res = bool(self.click_image_logic(step))
            if not res and self.running and not step.get("skip_maintain"):
                self.execute_step({"action": "handle_maintenance", "skip_maintain": True})
            return res
        elif action == "click_image_if":
            matched_path = self.click_image_logic(step)
            if matched_path:
                if step.get("success") and self._loop_success_stack:
                    self._loop_success_stack[-1] = True
                for sub_step in step.get("then", []):
                    if not self.execute_step(sub_step): 
                        return False
                
                # Nếu sai mật khẩu, báo lỗi để skip tài khoản (không retry)
                if matched_path and "sai_pass.jpg" in matched_path:
                    self.log("!! PHÁT HIỆN SAI MẬT KHẨU: Bỏ qua tài khoản này.")
                    self.skip_all_retries = True
                    return False
            res = True
        elif action == "click_coords":
            res = self.click_coords_logic(step)
        elif action == "wait":
            wait_time = step.get("duration") or step.get("timeout") or 1
            start_wait = time.time()
            while time.time() - start_wait < wait_time and self.running:
                time.sleep(0.5)
            res = True
        elif action == "clear_android_data":
            pkg = step.get("package")
            self.call_adb(["shell", "pm", "clear", pkg])
            res = True
        elif action == "input_account":
            res = self.input_account_logic()
        elif action == "input_password":
            res = self.input_password_logic()
        elif action == "search":
            res = self.search_logic(step)
        elif action == "click_any":
            res = self.click_any_logic(step)
        elif action == "press_esc":
            res = self.press_esc_logic(step)
        elif action == "verify_or_restart":
            res = self.verify_or_restart_logic(step)
        elif action == "mark_success":
            if self.current_account:
                self.current_account["success"] = True
            res = True
        elif action == "cases":
            res = self.cases_logic(step)
            if not res and self.running and not step.get("skip_maintain") and "timeout_then" not in step:
                self.execute_step({"action": "handle_maintenance", "skip_maintain": True})
            
            if not res and "timeout_then" in step:
                self.log(f"!! [DEBUG] Bước 'cases' bị Timeout sau {step.get('timeout', 10)}s. Đang gọi logic xử lý Timeout (handle_maintenance)...")
                for sub_step in step.get("timeout_then", []):
                    if not self.execute_step(sub_step):
                        return False
                return True # Đã xử lý bằng timeout_then, coi như bước này thành công
            return res # Trả về True nếu khớp case, False nếu timeout mà không có timeout_then
        # elif action == "restart_app":
        #     app = step.get("app", "com.garena.game.kgvn")
        #     self.log(f"!! PHÁT HIỆN LỖI: Đóng game và khởi động lại {app}...")
        #     self.force_stop_game()
        #     self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
        #     self.log("Đợi game khởi động lại (20s)...")
        #     start_wait = time.time()
        #     while time.time() - start_wait < 20 and self.running:
        #         time.sleep(0.5)
        #     return False
        elif action == "handle_maintenance":
            # Tự động tìm package game có trên máy
            potential_apps = ["com.garena.game.kgvn64x", "com.garena.game.kgvn", "com.garena.game.kgtw"]
            app = "com.garena.game.kgvn" # Mặc định
            for p in potential_apps:
                check = self.call_adb(["shell", "pm", "path", p])
                if check.returncode == 0 and check.stdout.strip():
                    app = p
                    break
            
            if getattr(self, 'chest_claimed', False):
                self.log("!! Lỗi sau khi nhận rương: Chỉ thực hiện đăng xuất...")
                for _ in range(2): self.call_adb(["shell", "input", "keyevent", "4"]); time.sleep(1)
                self.execute_step({"action": "click_image", "target1": "images_cs187_cs187/setting.jpg", "target2": "images_cs187/setting1.jpg", "timeout": 10, "skip_maintain": True})
                time.sleep(2)
                self.execute_step({"action": "click_image", "target1": "images_cs187/logout.jpg", "target2": "images_cs187/logout_big.jpg", "timeout": 20, "skip_maintain": True})
                time.sleep(2)
                self.execute_step({"action": "click_image", "target": "images_cs187/ok_cs1.jpg", "timeout": 20, "skip_maintain": True})
                
                # Fallback nếu UI logout thất bại
                if not self.search_logic({"target": "images_cs187/login_garena2.jpg", "timeout": 5, "confidence": 0.8}):
                    self.force_stop_game()
                    self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                    self.log("Đợi game mở và nhấn Garena...")
                    self.execute_step({"action": "click_image_if", "target": "images_cs187/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
                    time.sleep(5)
                return False
            elif getattr(self, 'code_entered', False):
                self.log("!! PHÁT HIỆN LỖI (Đã nhập mã): Đang thực hiện đăng xuất...")
                for _ in range(2): self.call_adb(["shell", "input", "keyevent", "4"]); time.sleep(1)
                if self.execute_step({"action": "click_image", "target1": "images_cs187/setting.jpg", "target2": "images_cs187/setting1.jpg", "timeout": 10, "skip_maintain": True}):
                    time.sleep(2)
                    self.execute_step({"action": "click_image", "target1": "images_cs187/logout.jpg", "target2": "images_cs187/logout_big.jpg", "timeout": 20, "skip_maintain": True})
                    time.sleep(2)
                    self.execute_step({"action": "click_image", "target": "images_cs187/ok_cs1.jpg", "timeout": 20, "skip_maintain": True})
                    time.sleep(5)
                
                if not self.search_logic({"target": "images_cs187/login_garena2.jpg", "timeout": 5, "confidence": 0.8}):
                    self.force_stop_game()
                    self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                    self.log("Đợi game mở và nhấn Garena...")
                    self.execute_step({"action": "click_image_if", "target": "images_cs187/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
                    time.sleep(5)
                return False
            elif getattr(self, 'is_login_phase', False):
                self.log(f"!! LỖI TRONG KHI ĐĂNG NHẬP: Restart {app} và thử lại từ đầu...")
                self.force_stop_game()
                self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                self.skip_login_for_this_acc = False # Quan trọng: Không bỏ qua login
                time.sleep(5)
                return False
            # else:
            #     self.log(f"!! PHÁT HIỆN BẢO TRÌ/LỖI: Tiến hành Restart {app}...")
            #     self.force_stop_game()
            #     self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
            #     self.skip_login_for_this_acc = True
            #     self.log("Đợi game mở và nhấn Garena...")
            #     self.execute_step({"action": "click_image_if", "target": "images_cs187/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
            #     time.sleep(5)
            #     if self.search_logic({"target1": "images_cs187/account_input1.jpg", "target2": "images_cs187/account_input.png", "target3": "images_cs187/account.jpg", "timeout": 5}):
            #         self.log("!! PHÁT HIỆN CHƯA ĐĂNG NHẬP (THẤY INPUT): TIẾN HÀNH ĐĂNG NHẬP LẠI.")
            #         self.skip_login_for_this_acc = False # Yêu cầu chạy kịch bản login
            #     return False
        elif action == "long_click":
            duration = step.get("duration", 5000)
            res = self.long_click_logic(step, duration)
        elif action == "loop":
            count = step.get("count", 1)
            sub_steps = step.get("steps", [])
            until_img = step.get("until")
            has_success_step = any(s.get("success") for s in sub_steps)
            self._loop_success_stack.append(False)

            for i in range(count):
                if not self.running: return False
                if until_img and self.search_logic({"target": until_img, "timeout": 3, "confidence": 0.9}):
                    self.log(f"==> [LOOP] Đã tìm thấy {os.path.basename(until_img)}, dừng loop.")
                    break
                for s in sub_steps:
                    if not self.execute_step(s): 
                        self._loop_success_stack.pop()
                        return False
                if self._loop_success_stack[-1]:
                    break

            loop_success = self._loop_success_stack.pop()
            if has_success_step and not loop_success:
                return False
            res = True
        
        duration = time.time() - self.last_step_time
        if duration > 35: self.update_status("Lag", True)
        else: self.update_status("Đang chạy", False)
        return res
    def click_coords_logic(self, step):
        x, y = step.get("x"), step.get("y")
        if x is not None and y is not None:
            delay = step.get("timeout", 0)
            if delay > 0: time.sleep(delay)
            self.call_adb(["shell", "input", "tap", str(x), str(y)])
            self.log(f"CLICK TỌA ĐỘ: ({x}, {y})")
            return True
        return False
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

        # Sử dụng Cache để tránh đọc đĩa liên tục
        target_imgs = []
        for t_path in targets:
            img = get_cached_template(t_path, use_color)
            if img is not None:
                target_imgs.append((t_path, img))

        start = time.time()
        best_match = {"val": 0, "name": ""}
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                
                for t_path, t_img in target_imgs:
                    if t_img.shape[0] > compare_screen.shape[0] or t_img.shape[1] > compare_screen.shape[1]:
                        continue
                    res = cv2.matchTemplate(compare_screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, ml = cv2.minMaxLoc(res)
                    
                    if mv > best_match["val"]:
                        best_match = {"val": mv, "name": os.path.basename(t_path)}
                        
                    if mv >= confidence:
                        th_s, tw_s = t_img.shape[:2]
                        self.call_adb(["shell", "input", "tap", str(ml[0]+tw_s//2), str(ml[1]+th_s//2)])
                        del screen
                        if not use_color: del compare_screen
                        del res
                        return t_path
                    del res
                if not use_color: del compare_screen
            del screen
            time.sleep(1.5)
        return None

    def cases_logic(self, step):
        cases = step.get("cases", [])
        if not cases: return True
        timeout = step.get("timeout", 10)
        confidence = step.get("confidence", 0.8)
        
        # Cache templates để tăng tốc độ xử lý
        case_templates = []
        for case in cases:
            triggers = []
            if case.get("trigger"): triggers.append(case.get("trigger"))
            idx = 1
            while f"trigger{idx}" in case:
                triggers.append(case.get(f"trigger{idx}")); idx += 1
            
            loaded_triggers = []
            for t_path in triggers:
                t_img = get_cached_template(t_path, use_color=False)
                if t_img is not None:
                    loaded_triggers.append((t_path, t_img))
            
            if loaded_triggers:
                case_templates.append({
                    "triggers": loaded_triggers,
                    "confidence": case.get("confidence", confidence),
                    "script": case.get("script", [])
                })

        start_time = time.time()
        while time.time() - start_time < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(1); continue
            
            scr_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            del screen
            
            matched_item = None
            for item in case_templates:
                for t_path, t_img in item["triggers"]:
                    if t_img.shape[0] > scr_gray.shape[0] or t_img.shape[1] > scr_gray.shape[1]:
                        continue
                    res = cv2.matchTemplate(scr_gray, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    del res
                    if mv >= item["confidence"]:
                        matched_item = item
                        break
                if matched_item: break
            del scr_gray
            
            if matched_item:
                for s_step in matched_item["script"]:
                    if not self.running: return False
                    if not self.execute_step(s_step):
                        return False
                return True
            time.sleep(1)
        return False
def search_logic(self, step):
        targets = []
        if step.get("target"): targets.append(step.get("target"))
        i = 1
        while f"target{i}" in step:
            targets.append(step.get(f"target{i}"))
            i += 1
            
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        use_color = step.get("use_color", False)
        
        target_imgs = []
        for t_path in targets:
            img = get_cached_template(t_path, use_color)
            if img is not None:
                target_imgs.append(img)
        
        if not target_imgs: return False
        
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                compare_screen = screen if use_color else cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                found = False
                for t_img in target_imgs:
                    if t_img.shape[0] > compare_screen.shape[0] or t_img.shape[1] > compare_screen.shape[1]:
                        continue
                    res = cv2.matchTemplate(compare_screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    del res
                    if mv >= conf:
                        found = True
                        break
                if not use_color: del compare_screen
                del screen
                if found: return True
            time.sleep(1)
        return False

def click_any_logic(self, step):
        wait_time = step.get("wait") or 0
        if wait_time > 0: time.sleep(wait_time)
        screen = self.get_screenshot()
        if screen is not None:
            h, w = screen.shape[:2]
            # Click thấp xuống một chút (60% màn hình) thay vì giữa (50%)
            self.call_adb(["shell", "input", "tap", str(w//2), str(int(h * 0.6))])
            return True
        return False

def long_click_logic(self, step, duration):
        target = step.get("target")
        confidence = step.get("confidence", 0.8)
        timeout = step.get("timeout", 10)
        
        if target:
            t_img = get_cached_template(target, use_color=False)
            if t_img is None: return False
            
            start = time.time()
            while time.time() - start < timeout and self.running:
                screen = self.get_screenshot()
                if screen is not None:
                    scr_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    if t_img.shape[0] <= scr_gray.shape[0] and t_img.shape[1] <= scr_gray.shape[1]:
                        res = cv2.matchTemplate(scr_gray, t_img, cv2.TM_CCOEFF_NORMED)
                        _, mv, _, ml = cv2.minMaxLoc(res)
                        if mv >= confidence:
                            th_s, tw_s = t_img.shape[:2]
                            x, y = ml[0]+tw_s//2, ml[1]+th_s//2
                            self.call_adb(["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration)])
                            return True
                time.sleep(1)
            return False
        else:
            x, y = step.get("x", 0.5), step.get("y", 0.5)
            screen = self.get_screenshot()
            h, w = (screen.shape[:2]) if screen is not None else (540, 960)
            real_x = int(x * w) if isinstance(x, float) else x
            real_y = int(y * h) if isinstance(y, float) else y
            self.call_adb(["shell", "input", "swipe", str(real_x), str(real_y), str(real_x), str(real_y), str(duration)])
            return True

def verify_or_restart_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 15)
        
        potential_apps = ["com.garena.game.kgvn64x", "com.garena.game.kgvn", "com.garena.game.kgtw"]
        app = "com.garena.game.kgvn"
        for p in potential_apps:
            check = self.call_adb(["shell", "pm", "path", p])
            if check.returncode == 0 and check.stdout.strip():
                app = p
                break
        
        found = self.search_logic({"target": target, "timeout": timeout, "confidence": step.get("confidence", 0.7)})
        if found: 
            return True
        
        # self.log(f"!! KHÔNG THẤY {target}. TIẾN HÀNH KHỞI ĐỘNG LẠI {app}!")
        for p in potential_apps: self.call_adb(["shell", "am", "force-stop", p])
        time.sleep(2)
        self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
        
        # self.log("Đợi game khởi động lại và chạy restart_script...")
        r_script = step.get("script", [])
        for s in r_script:
            if not self.running: break
            self.execute_step(s)
            
        return False

def press_esc_logic(self, step):
        time.sleep(step.get("wait", 0))
        self.call_adb(["shell", "input", "keyevent", "4"])
        return True

def input_account_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("tk", "")
        # Không xóa nội dung trước đó nữa để tránh làm mất text đã nhập.
        self.input_text_robust(content)
        return True

def input_password_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("mk", "")
        # Không xóa nội dung trước đó nữa để tránh làm mất text đã nhập.
        self.input_text_robust(content)
        return True

def run(self, accounts, worker_index, shared_data):
        self.accounts_list = accounts
        self.worker_index = worker_index
        self.shared_data = shared_data
        self.running = True

        # --- TẢI KỊCH BẢN TỪ FILE NGOÀI NẾU CÓ ---
        script_file = "script.json"
        
        # Giá trị mặc định (Hardcoded)
        login_script = [
            {"action": "click_image_if", "target": "images_cs187/garena.png", "timeout": 45, "confidence": 0.8},
            {"action": "wait", "timeout": 2, "login_step": True},
            {"action": "input_account", "login_step": True},
            {"action": "click_coords", "x": 391, "y": 638, "timeout": 1},
            
            {"action": "input_password", "login_step": True},
            {"action": "click_coords", "x": 1718, "y": 533, "timeout": 1},
            {"action": "click_coords", "x": 1537, "y": 981, "timeout": 3},
            
                
               
                
            
            
            {"action": "click_image_if", "target": "images_cs187/batdau.png", "timeout": 4, "confidence": 0.85},
            {"action": "wait", "timeout": 17, "login_step": True},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
        
]
        # --- 1. ĐỊNH NGHĨA CÁC KỊCH BẢN CHUẨN ---
        nhay_script = [
            {"action": "click_image_if", "target1": "images_cs187/x.png", "target2": "images_cs187/x1.png", "timeout": 60, "confidence": 0.85},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            
            {"action": "click_coords", "x": 1759, "y": 226, "timeout": 2},  # sự kiện
            {"action": "click_coords", "x": 253, "y": 424, "timeout": 2},   # 18/7
            {"action": "click_coords", "x": 253, "y": 424, "timeout": 2},   # đăng nhập là trúng
            {"action": "click_coords", "x": 253, "y": 424, "timeout": 2},   # đăng nhập là trúng
            
            {"action": "click_coords", "x": 1682, "y": 997, "timeout": 3} ,  # collect
            {"action": "click_image", "target1": "images_cs187/back.png", "target2": "images_cs187/back1.png","timeout": 30, "confidence": 0.8},
            
            {"action": "click_coords", "x": 1561, "y": 45, "timeout": 2},
            {"action": "click_coords", "x": 197, "y": 311, "timeout": 2}, # hệ thống

            {"action": "click_coords", "x": 1105, "y": 989, "timeout": 2},# claim
            {"action": "click_coords", "x": 754, "y": 977, "timeout": 2},# claim
            {"action": "click_coords", "x": 754, "y": 977, "timeout": 2},# claim
            {"action": "press_esc", "wait": 1},
            {"action": "click_coords", "x": 1759, "y": 226, "timeout": 2},  # sự kiện
           
            {"action": "click_coords", "x": 241, "y": 311, "timeout": 2}, # sưu tầm
            {"action": "click_image", "target": "images_cs187/batdau.png", "timeout": 30, "confidence": 0.8},
            {"action": "click_image", "target": "images_cs187/goi.png", "timeout": 30, "confidence": 0.8},

            {"action": "click_coords", "x": 947, "y": 842, "timeout": 7},# chấp nhận
            {"action": "click_coords", "x": 770, "y": 965, "timeout": 2},
            {"action": "click_coords", "x": 770, "y": 965, "timeout": 2},
            {"action": "click_coords", "x": 770, "y": 965, "timeout": 2},
            # qh
            {"action": "click_image", "target": "images_cs187/hoanhthanh.png", "timeout": 30, "confidence": 0.8},
            {"action": "click_image", "target1": "images_cs187/back.png", "target2": "images_cs187/back1.png","timeout": 30, "confidence": 0.8},
            {"action": "click_image_if", "target1": "images_cs187/back.png", "target2": "images_cs187/back1.png","timeout": 5, "confidence": 0.8},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_coords", "x": 1601, "y": 468, "timeout": 2},
            {"action": "click_coords", "x": 177, "y": 513, "timeout": 1},
            {"action": "click_coords", "x": 177, "y": 513, "timeout": 1},
            {"action": "click_coords", "x": 177, "y": 513, "timeout": 1},
            {"action": "click_coords", "x": 1177, "y": 343, "timeout": 1},
            {"action": "click_coords", "x": 1177, "y": 343, "timeout": 1},


        ]

        dang_xuat_script = [
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_coords", "x": 1670, "y": 37, "timeout": 2},
            {"action": "click_coords", "x": 1706, "y": 989, "timeout": 2},
            {"action": "click_coords", "x": 1165, "y": 775, "timeout": 2},
           
        ]
       
        if os.path.exists(script_file):
            try:
                with open(script_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "login_script" in data: login_script = data["login_script"]
                    if "nhay_script" in data: nhay_script = data["nhay_script"]
                    if "dang_xuat_script" in data: dang_xuat_script = data["dang_xuat_script"]
                    self.log(f"==> ĐÃ TẢI KỊCH BẢN TỪ {script_file}")
            except Exception as e:
                self.log(f"!! LỖI khi tải {script_file}: {str(e)}")

        # --- 2. VÒNG LẶP CHẠY DANH SÁCH TÀI KHOẢN ---
        while self.running:
            self.current_account = None
            with FILE_LOCK:
                for acc in self.accounts_list:
                    if not acc.get("used"):
                        acc["used"] = True
                        self.current_account = acc
                        self.update_ui_func()
                        break
            if not self.current_account: 
                break
                
            self.log(f">> START: {self.current_account['tk']}")
            self.skip_login_for_this_acc = False
            self.chest_claimed = False
            
            while self.running:
                self.skip_all_retries = False
                success = False
                
                # --- 2.1. ĐĂNG NHẬP ---
                success_login = False
                self.is_login_phase = True
                for retry_login in range(3):
                    if self.search_logic({"target1": "images_cs187/su_kien.jpg", "target2": "images_cs187/setting.jpg", "target3": "images_cs187/su_kien2.jpg", "timeout": 5, "confidence": 0.7}):
                        self.log("==> ĐÃ Ở TRONG SẢNH, BỎ QUA ĐĂNG NHẬP.")
                        success_login = True
                        break
                        
                    success_login = True
                    for step in login_script:
                        if not self.running: break
                        if self.skip_login_for_this_acc and step.get("login_step"): continue
                        if not self.execute_step(step):
                            success_login = False
                            break
                    if success_login or not self.running or self.skip_all_retries: 
                        break
                    self.log(f"!! Login thất bại (vòng {retry_login+1}/3). Đang bắt đầu lại...")
                    self.skip_login_for_this_acc = False
                
                if not success_login or self.skip_all_retries or not self.running:
                    if self.skip_all_retries:
                        self.report_stats_func(False, f"{self.current_account['tk']}|{self.current_account['mk']} (SAI PASS)")
                        break
                    if not self.running: break
                    continue
                
                self.is_login_phase = False

                # --- 2.2. THỰC HIỆN CÁC BƯỚC CLICK TRONG SCRIPT NHẢY ---
                success_nhay = True
                decisive_failure = False
                self.chest_claimed = False
                
                for step in nhay_script:
                    if not self.running: 
                        break
                    
                    if decisive_failure and step.get("target") == "images_cs187/xac_nhan_ruong_ss.jpg":
                        continue
                        
                    if not self.execute_step(step):
                        if step.get("decisive_failure"):
                            decisive_failure = True
                            continue 
                        else:
                            success_nhay = False
                            break
                    
                    if step.get("target") == "images_cs187/xac_nhan_ruong_ss.jpg":
                        self.chest_claimed = True
                
                # --- 2.3. ĐOẠN MỚI: VÒNG LẶP QUÉT TÌM VẬT PHẨM ĐẶC BIỆT QUA OCR ---
                found_item = False
                if self.running and success_nhay:
                    self.log("=== BẮT ĐẦU VÒNG LẶP OCR QUÉT TÌM VẬT PHẨM ĐẶC BIỆT ===")
                    max_retry_ocr = 1
                    
                    for attempt in range(max_retry_ocr):
                        if not self.running: 
                            break
                            
                        self.log(f"Đang quét tìm vật phẩm lần {attempt + 1}/{max_retry_ocr}...")
                        
                        # Thực hiện quét vùng tọa độ chỉ định
                        ket_qua_quet = self.quet_tu_khoa_ocr(267, 586, 1670, 702)
                        
                        if ket_qua_quet:
                            self.log("🎉 XÁC NHẬN: Tìm thấy Valhein TNVT hoặc Liliana MPTT!")
                            found_item = True
                            
                            # Định dạng thông tin acc để ghi ra file riêng
                            acc_info = f"{self.current_account['tk']}|{self.current_account['mk']}"
                            try:
                                with open("tai_khoan_trung.txt", "a", encoding="utf-8") as file_out:
                                    file_out.write(f"{acc_info} | Trúng lúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                self.log("💾 Đã xuất thông tin tài khoản thành công vào file 'tai_khoan_trung.txt'")
                            except Exception as e:
                                self.log(f"LỖI ghi file txt: {e}")
                                
                            break  # Tìm thấy vật phẩm yêu cầu -> Ngắt vòng lặp OCR ngay lập tức
                        
                        time.sleep(1.5)  # Chờ hiệu ứng chuyển động/lật thẻ game
                    
                    if not found_item:
                        self.log("⚠️ Không tìm thấy từ khóa yêu cầu ở acc này.")

                # --- 2.4. ĐĂNG XUẤT ---
                if self.running and success_nhay:
                    for step in dang_xuat_script:
                        if not self.running: break
                        if not self.execute_step(step): break

                # --- 2.5. KẾT THÚC VÀ ĐỔI ACCOUNT KẾ TIẾP ---
                if self.running:
                    if decisive_failure:
                        self.report_stats_func(False, f"{self.current_account['tk']}|{self.current_account['mk']} (KHÔNG THẤY RƯƠNG)")
                        break
                    elif success_nhay or self.chest_claimed:
                        self.current_account["success"] = True
                        self.report_stats_func(True, f"{self.current_account['tk']}|{self.current_account['mk']}")
                        self.skip_login_for_this_acc = False
                        break
                    else:
                        self.log(f"!! Lỗi thực thi Script Nhảy, đang thử lại: {self.current_account['tk']}")
                        time.sleep(2)
            
            gc.collect()

        self.log(">> LUỒNG ĐÃ DỪNG HOÀN TOÀN.")
        self.update_status("Đã dừng")
        self.running = False


# Gắn các helper ở module level vào class để code cũ vẫn chạy đúng.
AutoClickerInstance.press_esc_logic = press_esc_logic
AutoClickerInstance.input_account_logic = input_account_logic
AutoClickerInstance.input_password_logic = input_password_logic
AutoClickerInstance.search_logic = search_logic
AutoClickerInstance.click_any_logic = click_any_logic
AutoClickerInstance.long_click_logic = long_click_logic
AutoClickerInstance.verify_or_restart_logic = verify_or_restart_logic
AutoClickerInstance.run = run


class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AUTO NHAY LQ - PRO")
        self.geometry("1000x650")
        self.configure(fg_color=BG_COLOR)
        self.accounts_data = []
        self.account_file_path = None
        self.instances = []
        self.active_workers = []
        self.success_count = 0
        self.failure_count = 0
        self.total_accounts_loaded = 0
        self.shared_data = {
            "lock": threading.Lock()
        }
        self.adb_path = self.find_adb()
        self.device_map = {}
        self.device_cards = {}
        
        try:
            self.logo_img = ctk.CTkImage(Image.open(resource_path("nhay_script_logo.png")), size=(80, 80))
            self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
            self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))
        except:
            self.logo_img = self.start_icon = self.stop_icon = None
        
        self.setup_layout()
        self.scan_devices()
        


    def setup_layout(self):
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=NAV_COLOR); self.sidebar.pack(side="left", fill="y")
        if self.logo_img: ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=20)
        ctk.CTkLabel(self.sidebar, text="NHAY SCRIPT PRO", font=("Arial", 18, "bold"), text_color=ACCENT_GREEN).pack()
        
        self.account_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10); self.account_card.pack(padx=15, pady=10, fill="x")
        ctk.CTkButton(self.account_card, text="NẠP FILE ACC", command=self.load_accounts, fg_color="#f59e0b", hover_color="#d97706", text_color="#fff", font=("Segoe UI", 11, "bold"), height=32).pack(pady=10, padx=10, fill="x")

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

        self.main_content = ctk.CTkFrame(self, fg_color="transparent"); self.main_content.pack(side="right", fill="both", expand=True, padx=20, pady=15)
        
        # --- HEADER & STATS CARDS ---
        stats_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        stats_container.pack(fill="x", pady=(0, 10))
        
        # Thẻ Tổng Acc
        self.card_acc = ctk.CTkFrame(stats_container, fg_color=CARD_COLOR, height=80, corner_radius=12, border_width=1, border_color="#333")
        self.card_acc.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(self.card_acc, text="TỔNG TÀI KHOẢN", font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(pady=(10, 0))
        self.acc_count_val = ctk.CTkLabel(self.card_acc, text="0", font=("Segoe UI", 28, "bold"), text_color="#38bdf8")
        self.acc_count_val.pack(pady=(0, 5))

        # Thẻ Thành Công
        self.card_success = ctk.CTkFrame(stats_container, fg_color=CARD_COLOR, height=80, corner_radius=12, border_width=1, border_color="#333")
        self.card_success.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ctk.CTkLabel(self.card_success, text="SỐ ACC THÀNH CÔNG", font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(pady=(10, 0))
        self.success_val = ctk.CTkLabel(self.card_success, text="0", font=("Segoe UI", 28, "bold"), text_color="#34d399")
        self.success_val.pack(pady=(0, 5))

        # --- DEVICE LIST SECTION ---
        inst_header = ctk.CTkFrame(self.main_content, fg_color="transparent")
        inst_header.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(inst_header, text="DANH SÁCH THIẾT BỊ", font=("Segoe UI", 13, "bold"), text_color=ACCENT_GREEN).pack(side="left")
        self.device_count_lbl = ctk.CTkLabel(inst_header, text="(0)", font=("Segoe UI", 13, "bold"), text_color="#38bdf8")
        self.device_count_lbl.pack(side="left", padx=5)
        
        self.btn_refresh = ctk.CTkButton(inst_header, text="Làm Mới ADB", command=self.scan_devices, width=100, height=28, font=("Segoe UI", 11, "bold"), fg_color="#334155", hover_color="#475569")
        self.btn_refresh.pack(side="right")
        
        self.device_list_frame = ctk.CTkScrollableFrame(self.main_content, height=450, fg_color="#111", corner_radius=12, border_width=1, border_color="#222")
        self.device_list_frame.pack(fill="both", expand=True, pady=10)
        
        self.load_adb_config()

    def find_adb(self):
        local_adb = resource_path("adb.exe")
        paths = [local_adb, "adb", r"C:\LDPlayer\LDPlayer9db.exe"]
        for p in paths:
            try:
                if p == "adb" or os.path.exists(p):
                    subprocess.run([p, "version"], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                    return p
            except: continue
        return "adb"

    def save_adb_and_refresh(self):
        path = self.adb_path_entry.get().strip()
        if not path: self.adb_path = "adb"
        else:
            if os.path.isdir(path): path = os.path.join(path, "adb.exe")
            if os.path.exists(path) or path == "adb": self.adb_path = path
            else:
                self.add_log(f"LỖI: Không tìm thấy file adb tại {path}")
                return
        try:
            with open("adb_config.txt", "w") as f: f.write(self.adb_path)
            self.adb_path_entry.delete(0, 'end'); self.adb_path_entry.insert(0, self.adb_path)
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
                        self.adb_path_entry.delete(0, 'end'); self.adb_path_entry.insert(0, self.adb_path)
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
            serials.sort()
        except Exception as e: print(f"Lỗi quét ADB: {e}")
        self.after(0, lambda: self._update_device_list_ui(serials))

    def _update_device_list_ui(self, serials):
        self.device_count_lbl.configure(text=f"({len(serials)})")
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        # Configure grid columns for the scrollable frame
        self.device_list_frame.grid_columnconfigure((0, 1, 2), weight=1, pad=10)
        
        for i, s in enumerate(serials):
            self.device_map[s] = i
            
            # Create a card for each device
            row = i // 3
            col = i % 3
            
            dev_box = ctk.CTkFrame(self.device_list_frame, fg_color="#18181b", corner_radius=12, border_width=1, border_color="#27272a")
            dev_box.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)
            
            # Device Header (Index + Serial)
            header = ctk.CTkFrame(dev_box, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(8, 2))
            ctk.CTkLabel(header, text=f"BOX #{i+1:02d}", font=("Segoe UI", 12, "bold"), text_color="#38bdf8").pack(side="left")
            ctk.CTkLabel(header, text=f"[{s[-4:]}]", font=("Consolas", 10), text_color="#64748b").pack(side="right")
            
            # Status Section
            status_frame = ctk.CTkFrame(dev_box, fg_color="#09090b", corner_radius=8)
            status_frame.pack(fill="x", padx=10, pady=5)
            status_lbl = ctk.CTkLabel(status_frame, text="Sẵn sàng", font=("Segoe UI", 11), text_color="#64748b")
            status_lbl.pack(pady=4)
            
            # Control Buttons
            btn_frame = ctk.CTkFrame(dev_box, fg_color="transparent")
            btn_frame.pack(fill="x", padx=10, pady=(2, 10))
            
            b_stop = ctk.CTkButton(btn_frame, text="DỪNG", width=60, height=26, fg_color="#3f3f46", hover_color="#ef4444", font=("Segoe UI", 10, "bold"), command=lambda sn=s: self.stop_single_device(sn))
            b_stop.pack(side="left", expand=True, padx=(0, 2))
            
            b_start = ctk.CTkButton(btn_frame, text="CHẠY", width=60, height=26, fg_color="#10b981", hover_color="#059669", font=("Segoe UI", 10, "bold"), command=lambda sn=s: self.start_single_device(sn))
            b_start.pack(side="right", expand=True, padx=(2, 0))
            
            self.device_cards[s] = {"status": status_lbl, "start_btn": b_start, "stop_btn": b_stop}

        self.btn_refresh.configure(state="normal", text="Làm Mới")
        if not serials: 
            lbl = ctk.CTkLabel(self.device_list_frame, text="Không tìm thấy thiết bị nào.", text_color="#888")
            lbl.grid(row=0, column=0, columnspan=3, pady=20)

    def load_accounts(self):
        p = fd.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not p: return
        self.account_file_path = p
        self.accounts_data = []
        with open(p, 'r', encoding='utf-8') as f:
            for l in f:
                parts = l.strip().split('|', 1)
                if len(parts)>=2: self.accounts_data.append({"tk":parts[0], "mk":parts[1], "used":False})
        self.total_accounts_loaded = len(self.accounts_data)
        self.add_log(f"Đã nạp {self.total_accounts_loaded} acc.")
        self.update_all_ui()

    def start_all(self):
        if not self.accounts_data: 
            self.add_log("Vui lòng nạp file tài khoản trước.")
            return
        
        serials = sorted(self.device_map.keys())
        for s in serials:
            self.start_single_device(s)
        self._schedule_gc()

    def stop_all(self):
        for w in self.active_workers:
            w.running = False
        for s in self.device_cards:
            self.device_cards[s]["status"].configure(text="Stopping...", text_color="#F87171")
        self.add_log("Đã gửi lệnh dừng tới tất cả thiết bị.")

    def start_single_device(self, serial):
        self.active_workers = [w for w in self.active_workers if w.running]
        for w in self.active_workers:
            if w.device_id == serial and w.running: return

        def update_single_status():
             if serial in self.device_cards:
                 found = False
                 for w in self.active_workers:
                     if w.device_id == serial:
                         self.device_cards[serial]["status"].configure(text=w.status, text_color="#4ADE80" if not w.is_lagging else "#FB7185")
                         found = True
                         break
                 if not found:
                     self.device_cards[serial]["status"].configure(text="Ready", text_color="#888")
             self.update_all_ui()

        worker = AutoClickerInstance(serial, self.adb_path, self.add_log, update_single_status, self.report_stats)
        self.active_workers.append(worker)
        threading.Thread(target=worker.run, args=(self.accounts_data, self.device_map[serial], self.shared_data), daemon=True).start()
        self.add_log(f"Đã bắt chạy thiết bị: {serial}")

    def stop_single_device(self, serial):
        for w in self.active_workers:
            if w.device_id == serial:
                w.running = False
        if serial in self.device_cards:
            self.device_cards[serial]["status"].configure(text="Stopping...", text_color="#F87171")

    def _schedule_gc(self):
        """Cleanup zombie workers và giải phóng bộ nhớ định kỳ mỗi 30 giây."""
        self.active_workers = [w for w in self.active_workers if w.running]
        gc.collect()
        self._gc_timer = self.after(30000, self._schedule_gc)

    def report_stats(self, success, info):
        if success: self.success_count += 1
        else: self.failure_count += 1
        
        fn = "SUCCESS_ACCS.txt" if success else "FAILED_ACCS.txt"
        status_text = "THÀNH CÔNG" if success else "THẤT BẠI"
        self.add_log(f"[{status_text}] {info}")
        with FILE_LOCK:
            with open(fn, "a", encoding="utf-8") as f: f.write(f"{info}\n")

        self.after(0, self.update_all_ui)

    def update_all_ui(self):
        self.success_val.configure(text=str(self.success_count))
        self.acc_count_val.configure(text=str(self.total_accounts_loaded))

    def add_log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] {text}")

    def _safe_append_log(self, msg):
        pass

if __name__ == "__main__":
    app = MultiPremiumApp()
    app.mainloop()

# pyinstaller --noconfirm --onefile --windowed --icon "nhay_script_logo.png" --name "AutoNhayLQ_Pro" --add-data "images_cs187;images_cs187" --add-data "nhay_script_logo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool_cs_nhay.py

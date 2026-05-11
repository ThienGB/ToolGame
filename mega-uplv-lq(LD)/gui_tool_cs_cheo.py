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
import urllib.request
import ssl
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

import tkinter.filedialog as fd

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

    def force_stop_game(self):
        self.log("-> Đang thực hiện đóng ứng dụng triệt để...")
        # 1. Nhấn Home để thoát về launcher trước
        self.call_adb(["shell", "input", "keyevent", "3"])
        time.sleep(1)
        # 2. Force stop các package liên quan
        apps = ["com.garena.game.kgvn"]
        for app in apps:
            self.call_adb(["shell", "am", "force-stop", app])
            self.call_adb(["shell", "pkill", "-f", app])
        time.sleep(2)

    def get_screenshot(self):
        try:
            cmd = [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"]
            try:
                process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                if process.returncode != 0: raise Exception("Lỗi exec-out")
                image_bytes = process.stdout
            except:
                cmd_fallback = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
                process = subprocess.run(cmd_fallback, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                image_bytes = process.stdout.replace(b"\r\n", b"\n")

            if not image_bytes: return None
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            self.log(f"LỖI Chụp màn hình: {str(e)}")
            return None
            
    def get_clipboard(self):
        """Đọc clipboard bằng cách ép buộc App Clipper lên Foreground để sync (Fix Android 10+)."""
        pkg = "com.example.clipper"
        path_in_android = f"/sdcard/Android/data/{pkg}/files/clip.txt"
        
        # 1. Ép buộc mở App Clipper lên (Dùng monkey cho chắc chắn 100%)
        self.log("[CLIPBOARD] Đang đồng bộ...")
        self.call_adb(["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"])
        time.sleep(1.5) # Đợi app hiện lên, sync và tự ẩn mình
        
        # 2. Đọc file kết quả
        cmd = [self.adb_path, "-s", self.device_id, "shell", f"cat {path_in_android} 2>/dev/null"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        except subprocess.TimeoutExpired:
            self.log("!! [CLIPBOARD] Timeout khi đọc clipboard.")
            return ""
        
        if not res.stdout: 
            self.log("!! [CLIPBOARD] File trống hoặc chưa có mã.")
            return ""
        
        try:
            raw_output = res.stdout.decode('utf-8', errors='ignore').strip()
        except:
            return ""

        if not raw_output: return ""
        
        lines = raw_output.split('\n')
        clean_lines = [l.strip() for l in lines if l.strip() and "adb" not in l.lower() and "*" not in l]
        
        if clean_lines:
            content = clean_lines[-1]
            
            # --- LỌC LẤY MÃ MỜI GIỮA HAI DẤU GẠCH NGANG -- ---
            import re
            match = re.search(r'--([A-Za-z0-9]+)--', content)
            if match:
                content = match.group(1)
                self.log(f"==> [CLIPBOARD] Đã lọc mã mời: {content}")
            else:
                self.log(f"==> [CLIPBOARD] Lấy mã thành công (Raw): {content}")
            
            return content
        
        return ""
        # service call clipboard 2 i32 1 (lấy dữ liệu clipboard)
        try:
            cmd_service = [self.adb_path, "-s", self.device_id, "shell", "service call clipboard 2 i32 1"]
            res_service = subprocess.run(cmd_service, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            # Kết quả service call cần parse rất phức tạp (HEX), nên đây chỉ là phương án dự phòng
        except: pass

        # 3. Thất bại
        return ""



    def execute_step(self, step):
        if not self.running: return False
        action = step.get("action")
        target_info = step.get("target") or step.get("target1", "")
        # self.log(f"==> Bước: {action} {f'({target_info})' if target_info else ''}") # Tắt log bước chạy chi tiết trên UI
        self.last_step_time = time.time()
        res = True
        
        if action == "click_image":
            res = bool(self.click_image_logic(step))
            if not res and self.running and not step.get("skip_maintain"):
                self.execute_step({"action": "handle_maintenance", "skip_maintain": True})
            return res
        elif action == "click_image_if":
            matched_path = self.click_image_logic(step)
            if matched_path:
                for sub_step in step.get("then", []):
                    if not self.execute_step(sub_step): 
                        return False
                
                # Nếu sai mật khẩu, báo lỗi để skip tài khoản (không retry)
                if matched_path and "sai_pass.jpg" in matched_path:
                    self.log("!! PHÁT HIỆN SAI MẬT KHẨU: Bỏ qua tài khoản này.")
                    self.skip_all_retries = True
                    return False
            res = True
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
        elif action == "click_any":
            res = self.click_any_logic(step)
        elif action == "swipe":
            res = self.swipe_logic(step)
        elif action == "press_esc":
            res = self.press_esc_logic(step)
        elif action == "verify_or_restart":
            res = self.verify_or_restart_logic(step)
        elif action == "prepare_clipper":
            pkg = "com.example.clipper"
            # Khởi động Service của APK
            # self.log("Đang khởi động Clipper Service...")
            self.call_adb(["shell", "am", "start-foreground-service", f"{pkg}/.ClipboardService"])
            # Xóa file cũ để tránh nhận nhầm mã cũ
            self.call_adb(["shell", "rm", "-f", f"/sdcard/Android/data/{pkg}/files/clip.txt"])
            res = True
        elif action == "get_code":
            timeout = step.get("timeout", 10)
            start_get = time.time()
            self.last_captured_code = ""
            while time.time() - start_get < timeout and self.running:
                self.last_captured_code = self.get_clipboard()
                if self.last_captured_code:
                    self.log(f"==> KẾT QUẢ LẤY MÃ: {self.last_captured_code}")
                    break
                time.sleep(2)
            
            if not self.last_captured_code:
                self.log("!! KẾT QUẢ LẤY MÃ: Thất bại (Vui lòng kiểm tra APK Helper)")
            res = (self.last_captured_code != "")
        elif action == "input_partner_code":
            if not self.partner_code:
                self.log("!! KHÔNG CÓ MÃ ĐỐI PHƯƠNG ĐỂ NHẬP")
                return False
            self.log(f"-> ĐANG NHẬP MÃ: {self.partner_code}")
            time.sleep(1.5) # Đợi bàn phím/input box hiện hẳn lên
            # Xóa cũ chắc chắn hơn
            for _ in range(3):
                self.call_adb(["shell", "input", "keyevent"] + ["67"] * 10)
                time.sleep(0.2)
            self.input_text_robust(self.partner_code)
            time.sleep(1)
            self.code_entered = True
            res = True
        elif action == "mark_success":
            if self.current_account:
                self.current_account["success"] = True
            res = True
        elif action == "cases":
            res = self.cases_logic(step)
            
            if not res and "timeout_then" in step:
                self.log(f"!! [DEBUG] Bước 'cases' bị Timeout sau {step.get('timeout', 10)}s. Đang gọi logic xử lý Timeout...")
                for sub_step in step.get("timeout_then", []):
                    self.execute_step(sub_step)
                return False 
            return res 
        elif action == "restart_app":
            app = step.get("app", "com.garena.game.kgvn")
            self.log(f"!! PHÁT HIỆN LỖI: Đóng game và khởi động lại {app}...")
            self.force_stop_game()
            self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
            self.log("Đợi game khởi động lại (20s)...")
            start_wait = time.time()
            while time.time() - start_wait < 20 and self.running:
                time.sleep(0.5)
            return False
        elif action == "handle_maintenance":
            # Tự động tìm package game có trên máy
            potential_apps = ["com.garena.game.kgvn64x", "com.garena.game.kgvn", "com.garena.game.kgtw"]
            app = "com.garena.game.kgvn" # Mặc định
            for p in potential_apps:
                check = self.call_adb(["shell", "pm", "path", p])
                if check.returncode == 0 and check.stdout.strip():
                    app = p
                    break
            
            if self.code_entered:
                self.log("!! PHÁT HIỆN LỖI (Đã nhập mã): Đang thực hiện đăng xuất...")
                # Quy trình thoát ra Đăng nhập (như nhay script)
                for _ in range(2): self.call_adb(["shell", "input", "keyevent", "4"]); time.sleep(1)
                if self.execute_step({"action": "click_image", "target1": "images/setting.jpg", "target2": "images/setting1.jpg", "timeout": 10, "skip_maintain": True}):
                    time.sleep(2)
                    self.execute_step({"action": "click_image", "target1": "images/logout.jpg", "target2": "images/logout_big.jpg", "timeout": 20, "skip_maintain": True})
                    time.sleep(2)
                    self.execute_step({"action": "click_image", "target": "images/ok_cs1.jpg", "timeout": 20, "skip_maintain": True})
                    time.sleep(5)
                
                if not self.search_logic({"target": "images/login_garena2.jpg", "timeout": 5, "confidence": 0.8}):
                    for p in potential_apps: self.call_adb(["shell", "am", "force-stop", p])
                    time.sleep(2)
                    self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                    self.log("Đợi game mở và nhấn Garena...")
                    self.execute_step({"action": "click_image_if", "target": "images/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
                    time.sleep(5)

                self.log("[THÀNH CÔNG] Đã xử lý xong acc đã nhập mã.")
                self.current_account["success"] = True
            elif getattr(self, 'is_login_phase', False):
                self.log(f"!! LỖI TRONG KHI ĐĂNG NHẬP: Restart {app} và thử lại từ đầu...")
                for p in potential_apps: self.call_adb(["shell", "am", "force-stop", p])
                time.sleep(2)
                self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                self.skip_login_for_this_acc = False # Quan trọng: Không bỏ qua login
                time.sleep(5)
                return False
            else:
                self.log(f"!! PHÁT HIỆN BẢO TRÌ/LỖI: Tiến hành Restart {app}...")
                for p in potential_apps: self.call_adb(["shell", "am", "force-stop", p])
                time.sleep(2)
                self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
                self.skip_login_for_this_acc = True
                self.log("Đợi game mở và nhấn Garena...")
                self.execute_step({"action": "click_image_if", "target": "images/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
                time.sleep(5)
            return False
        elif action == "loop":
            count = step.get("count", 1)
            sub_steps = step.get("steps", [])
            for i in range(count):
                if not self.running: return False
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

        target_imgs = []
        use_color = step.get("use_color", False)

        for t_path in targets:
            real_path = resource_path(t_path)
            if os.path.exists(real_path):
                read_mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
                img = cv2.imread(real_path, read_mode)
                if img is not None: target_imgs.append((t_path, img))

        start = time.time()
        best_match = {"val": 0, "name": ""}
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                if not use_color: compare_screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                else: compare_screen = screen
                
                for t_path, t_img in target_imgs:
                    # Tỉ lệ 1:1, không scale
                    t_scaled = t_img

                    # Bỏ qua nếu template lớn hơn màn hình
                    if t_scaled.shape[0] > compare_screen.shape[0] or t_scaled.shape[1] > compare_screen.shape[1]:
                        continue
                    res = cv2.matchTemplate(compare_screen, t_scaled, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, ml = cv2.minMaxLoc(res)
                    
                    if mv > best_match["val"]:
                        best_match = {"val": mv, "name": os.path.basename(t_path)}
                        
                    if mv >= confidence:
                        th_s, tw_s = t_scaled.shape[:2]
                        self.call_adb(["shell", "input", "tap", str(ml[0]+tw_s//2), str(ml[1]+th_s//2)])
                        self.log(f"-> CLICK: {os.path.basename(t_path)} ({mv:.2f})")
                        del screen; del res
                        if not use_color: del compare_screen
                        return t_path
                    del res
                if not use_color: del compare_screen
            del screen
            time.sleep(1.5)
        
        self.log(f"!! Timeout: Không thấy ảnh. Cao nhất: {best_match['name']} ({best_match['val']:.2f})")
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
                real_path = resource_path(t_path)
                if os.path.exists(real_path):
                    t_img = cv2.imread(real_path, cv2.IMREAD_GRAYSCALE)
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
            
            for item in case_templates:
                for t_path, t_img in item["triggers"]:
                    # Tỉ lệ 1:1
                    if t_img.shape[0] > scr_gray.shape[0] or t_img.shape[1] > scr_gray.shape[1]:
                        continue
                        
                    res = cv2.matchTemplate(scr_gray, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    
                    if mv >= item["confidence"]:
                        # self.log(f"-> PHÁT HIỆN: {os.path.basename(t_path)} ({mv:.2f})")
                        for s_step in item["script"]:
                            if not self.running: break
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
                for t_img in target_imgs:
                    if t_img.shape[0] > compare_screen.shape[0] or t_img.shape[1] > compare_screen.shape[1]:
                        continue
                    res = cv2.matchTemplate(compare_screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    if mv >= conf: return True
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
            del screen
            return True
        return False

    def swipe_logic(self, step):
        screen = self.get_screenshot()
        h, w = (screen.shape[:2]) if screen is not None else (540, 960)
        def gv(v, m): return int(v*m) if isinstance(v, float) and v <= 1.0 else int(v)
        x1, y1 = gv(step.get("x1", 0.5), w), gv(step.get("y1", 0.8), h)
        x2, y2 = gv(step.get("x2", 0.5), w), gv(step.get("y2", 0.3), h)
        self.call_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(step.get("duration", 500))])
        if screen is not None: del screen
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
        
        self.log("Đợi game mở và nhấn Garena...")
        self.execute_step({"action": "click_image_if", "target": "images/login_garena2.jpg", "timeout": 30, "confidence": 0.7, "skip_maintain": True})
        time.sleep(5)
        
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

    def run(self, accounts, worker_index, shared_data):
        self.accounts_list = accounts
        self.worker_index = worker_index
        self.pair_id = self.worker_index // 2
        self.is_role_a = (self.worker_index % 2 == 0)
        self.role_name = "Máy A" if self.is_role_a else "Máy B"
        self.shared_data = shared_data
        self.running = True

        login_script = [
            {"action": "click_image_if", "target": "images/login_garena2.jpg", "timeout": 15, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/login_garena2.jpg", "timeout": 3, "confidence": 0.7, "login_step": True},
            {"action": "click_image", "target1": "images/account_input1.jpg","target2": "images/account_input.png", "target3": "images/account.jpg", "target4": "images/account_input_note8.jpg", "timeout": 60, "confidence": 0.7, "login_step": True},
            {"action": "input_account", "login_step": True},
            {"action": "click_image", "target1": "images/tiep_theo.jpg", "target2": "images/tiep_theo1.jpg", "target3": "images/tiep_theo2.png", "timeout": 60, "confidence": 0.7, "login_step": True},
            {"action": "input_password", "login_step": True},
            {"action": "wait", "timeout": 2, "login_step": True},
            {"action": "click_image", "target1": "images/xong.jpg", "target2": "images/xong1.jpg", "target3": "images/xong2.png", "timeout": 30, "confidence": 0.7, "login_step": True},
            {"action": "wait", "timeout": 5, "login_step": True},
            {"action": "click_image_if", "target1": "images/ok2.png", "target2": "images/ok_dang_nhap_cs.jpg", "timeout": 4, "confidence": 0.7, "login_step": True},
            {"action": "click_image_if", "target1": "images/ok2.png", "target2": "images/ok_dang_nhap_cs.jpg", "timeout": 2, "confidence": 0.7, "login_step": True},
            {"action": "wait", "timeout": 5, "login_step": True},
            {"action": "click_image_if", "target1": "images/login.png", "target2": "images/login_now.png", "target3": "images/dang_nhap1.jpg", "timeout": 7, "confidence": 0.7, "login_step": True, "then": [
                {"action": "click_image_if", "target1": "images/ok2.png", "target2": "images/ok_dang_nhap_cs.jpg", "timeout": 4, "confidence": 0.7},
                {"action": "click_image_if", "target": "images/sai_pass.jpg", "timeout": 5, "confidence": 0.8, "login_step": True, "then": [
                {"action": "clear_android_data", "package": "com.garena.gaslite"},
                {"action": "restart_app"}]
            },
            ]},
            
            {"action": "click_image_if", "target": "images/batdau.png", "timeout": 6, "confidence": 0.8},
            {"action": "press_esc", "wait": 2},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 3},
        ]
       
        copy_script = [
            {
                "action": "cases",  
                "timeout" : 60,
                "timeout_then": [{"action": "handle_maintenance"}],
                "cases": [
                    {
                        "trigger": "images/su_kien.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image", "target1": "images/su_kien.jpg","target2": "images/su_kien2.jpg", "timeout": 5, "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images/su_kien.jpg", "target2": "images/su_kien2.jpg", "timeout": 2, "confidence": 0.8},
                            {"action": "press_esc", "wait": 3},
                            {"action": "press_esc", "wait": 3},
                            {"action": "press_esc", "wait": 3},
                            {"action": "press_esc", "wait": 3},
                            {"action": "click_image", "target1": "images/su_kien_cs.jpg", "target2": "images/su_kien_cs1.jpg", "timeout": 10, "confidence": 0.8},
                            {"action": "click_image_if", "target1": "images/su_kien_cs.jpg", "target2": "images/su_kien_cs1.jpg", "timeout": 2, "confidence": 0.8},
                            {"action": "click_image_if", "target1": "images/su_kien_cs.jpg", "target2": "images/su_kien_cs1.jpg", "timeout": 2, "confidence": 0.8},
                            {"action": "click_image_if", "target": "images/buoc_nhay_chung_suc.jpg", "timeout": 10, "confidence": 0.8},
                            {"action": "press_esc", "wait": 2},
                            {"action": "click_image", "target": "images/invite_friend.jpg", "timeout": 5, "confidence": 0.7},
                            {"action": "click_image", "target": "images/sao_chep_ma.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/sao_chep_ma.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "get_code", "timeout": 10},
                            {"action": "wait", "timeout": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "click_image", "target": "images/nhap_ma_moi.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/nhap_ma_moi.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
                            {"action": "click_image", "target1": "images/input_gift_code.jpg", "target2": "images/input_gift_code1.jpg", "target3": "images/input_gift_code2.jpg", "target4": "images/input_gift_code3.jpg", "timeout": 20, "confidence": 0.7},
                        ]
                    },
                    {
                        "trigger1": "images/xac_nhan_chung_suc1.png",
                        "trigger2": "images/invite_friend.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "wait", "timeout": 5},
                            {"action": "press_esc", "wait": 1},
                            {"action": "press_esc", "wait": 1},
                            {"action": "press_esc", "wait": 1},
                            {"action": "press_esc", "wait": 1},
                            {"action": "click_image", "target": "images/invite_friend.jpg", "timeout": 5, "confidence": 0.7},
                            {"action": "press_esc", "wait": 3},
                            {"action": "click_image_if", "target": "images/invite_friend.jpg", "timeout": 5, "confidence": 0.7},
                            {"action": "click_image", "target": "images/sao_chep_ma.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/sao_chep_ma.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "get_code", "timeout": 10},
                            {"action": "wait", "timeout": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "click_image", "target": "images/nhap_ma_moi.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/nhap_ma_moi.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
                            {"action": "click_image", "target1": "images/input_gift_code.jpg", "target2": "images/input_gift_code1.jpg", "target3": "images/input_gift_code2.jpg", "target4": "images/input_gift_code3.jpg", "timeout": 20, "confidence": 0.7},
                        ]
                    }
                ]
            },
            {"action": "wait", "timeout": 5}
        ]
        
        input_code_script = [
            {"action": "input_partner_code"},
        ]
        
        confirm_script = [
            {"action": "click_image_if", "target": "images/ok_cs.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/xac_nhan_chung_suc.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "mark_success"},
            {"action": "click_image_if", "target": "images/xac_nhan_chung_suc1.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 1},
            {"action": "press_esc", "wait": 1},
            {"action": "click_image", "target": "images/back_sk1.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/back_sk1.jpg", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/back_sk1.jpg", "timeout": 2, "confidence": 0.7},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target1": "images/setting.jpg", "target2": "images/setting1.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target1": "images/logout.jpg", "target2": "images/logout_big.jpg", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/ok_cs1.jpg", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
        ]

        # Script bổ sung để tách nhỏ navigation

        goto_input_code_only = [
            {
                "action": "cases",
                "timeout" : 60,
                "timeout_then": [{"action": "handle_maintenance"}],
                "cases": [
                    {
                        "trigger1": "images/input_gift_code2.jpg",
                        "trigger2": "images/input_gift_code1.jpg",
                        "trigger3": "images/input_gift_code3.jpg",
                        "trigger4": "images/input_gift_code.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image", "target1": "images/input_gift_code2.jpg", "target2": "images/input_gift_code1.jpg", "target3": "images/input_gift_code3.jpg", "target4": "images/input_gift_code.jpg",  "timeout": 20,  "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images/input_gift_code1.jpg", "target2": "images/input_gift_code2.jpg", "target3": "images/input_gift_code3.jpg", "target4": "images/input_gift_code.jpg", "timeout": 2, "confidence": 0.7},
                        ]
                    },
                    {
                        "trigger": "images/su_kien.jpg",
                        "confidence": 0.7,
                        "script": [
                            {"action": "click_image", "target1": "images/su_kien.jpg","target2": "images/su_kien2.jpg", "timeout": 5, "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images/su_kien.jpg", "target2": "images/su_kien2.jpg", "timeout": 2, "confidence": 0.8},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "click_image", "target": "images/su_kien_cs.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/su_kien_cs.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/su_kien_cs.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/buoc_nhay_chung_suc.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "press_esc", "wait": 2},
                            {"action": "press_esc", "wait": 2},
                            {"action": "click_image", "target": "images/nhap_ma_moi.jpg", "timeout": 10, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/nhap_ma_moi.jpg", "timeout": 2, "confidence": 0.7},
                            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
                            {"action": "click_image", "target1": "images/input_gift_code2.jpg", "target2": "images/input_gift_code1.jpg", "target3": "images/input_gift_code3.jpg", "target4": "images/input_gift_code.jpg", "timeout": 20, "confidence": 0.7},
                            {"action": "click_image_if", "target1": "images/input_gift_code1.jpg", "target2": "images/input_gift_code2.jpg", "target3": "images/input_gift_code3.jpg", "target4": "images/input_gift_code.jpg", "timeout": 2, "confidence": 0.7},
                        ]
                    }
                ]
            },
            {"action": "wait", "timeout": 5},
        ]

        try:
            while self.running:
                self.current_account = None
                with FILE_LOCK:
                    for acc in self.accounts_list:
                        if not acc.get("used"):
                            acc["used"] = True; self.current_account = acc
                            self.update_ui_func(); break
                if not self.current_account: break
                self.log(f">> START {self.role_name}: {self.current_account['tk']}")
                self.skip_login_for_this_acc = False
                
                # --- VÒNG LẶP RETRY CHO CHÍNH TÀI KHOẢN NÀY ---
                while self.running:
                    self.last_captured_code = None
                    self.skip_all_retries = False
                    self.use_external_codes = False
                    self.code_entered = False
                    
                    # --- RESET SHARED CODE SLOTS FOR THIS PAIR ---
                    with self.shared_data["lock"]:
                        if self.pair_id not in self.shared_data["codes"]:
                            self.shared_data["codes"][self.pair_id] = {"A": None, "B": None, "acc_A": None, "acc_B": None}
                        if self.is_role_a: self.shared_data["codes"][self.pair_id]["A"] = None
                        else: self.shared_data["codes"][self.pair_id]["B"] = None
                    target_code = None
                    success = False
                    pkg = "com.example.clipper"
                    # Bật Service để hiện Nút nổi (Pill)
                    self.call_adb(["shell", "am", "start-foreground-service", f"{pkg}/.ClipboardService"])
                    # Xóa mã cũ
                    path_in_android = f"/sdcard/Android/data/{pkg}/files/clip.txt"
                    self.call_adb(["shell", "rm", "-f", path_in_android])

                    # --- THỰC HIỆN ĐĂNG NHẬP TRƯỚC ---
                    # self.update_status("Đang Login...")
                    success_login = False
                    self.is_login_phase = True
                    for retry_login in range(3):
                        # Check nếu đã ở trong sảnh rồi thì skip login luôn
                        if self.search_logic({"target1": "images/su_kien.jpg", "target2": "images/setting.jpg", "target3": "images/su_kien2.jpg", "timeout": 5, "confidence": 0.7}):
                            self.log("==> ĐÃ Ở TRONG SẢNH, BỎ QUA ĐĂNG NHẬP.")
                            success_login = True
                            break
                            
                        success_login = True
                        for step in login_script:
                            if not self.running: break
                            if self.skip_login_for_this_acc and step.get("login_step"): continue
                            if not self.execute_step(step):
                                success_login = False; break
                        if success_login or not self.running or self.skip_all_retries: break
                        self.log(f"!! Login thất bại (vòng {retry_login+1}/3). Đang bắt đầu lại...")
                        self.skip_login_for_this_acc = False # Nếu skip login thất bại, vòng sau hãy làm full login
                            
                    if not success_login or self.skip_all_retries or not self.running:
                        if self.skip_all_retries:
                            self.report_stats_func(False, f"{self.current_account['tk']} (SAI PASS)")
                            break
                        if not self.running: break
                        self.log(f"!! Lỗi đăng nhập, đang thử lại chính tài khoản: {self.current_account['tk']}")
                        continue
                    
                    self.is_login_phase = False
                
                    # --- QUYẾT ĐỊNH LOGIC: CHÉO CẶP HAY DÙNG FILE MÃ ---
                    with self.shared_data["ext_lock"]:
                        self.use_external_codes = len(self.shared_data.get("external_codes", [])) > 0

                    if self.use_external_codes:
                        success = True
                        target_code = None
                        with self.shared_data["ext_lock"]:
                            codes = self.shared_data.get("external_codes", [])
                            if codes:
                                item = codes[0]
                                target_code = item["code"]; item["count"] -= 1
                                if item["count"] <= 0: codes.pop(0)
                        
                        if not target_code: success = False
                        else:
                            for step in goto_input_code_only:
                                if not self.running: break
                                if not self.execute_step(step): success = False; break
                            
                            if success and self.running:
                                self.partner_code = target_code
                                if not self.execute_step(input_code_script[-1]): success = False
                                if success:
                                    for step in confirm_script:
                                        if not self.running: break
                                        if not self.execute_step(step): success = False; break
                            
                            if (not success or not self.running) and target_code:
                                with self.shared_data["ext_lock"]:
                                    codes = self.shared_data.get("external_codes", [])
                                    found = False
                                    for item in codes:
                                        if item["code"] == target_code: item["count"] += 1; found = True; break
                                    if not found: codes.insert(0, {"code": target_code, "count": 1})
                    else:
                        with self.shared_data["lock"]:
                            if self.pair_id not in self.shared_data["codes"]:
                                self.shared_data["codes"][self.pair_id] = {"A": None, "B": None, "acc_A": None, "acc_B": None}
                            if self.is_role_a: self.shared_data["codes"][self.pair_id]["acc_A"] = self.current_account
                            else: self.shared_data["codes"][self.pair_id]["acc_B"] = self.current_account
                        
                        success = True
                        for retry in range(2):
                            copy_ok = True
                            for step in copy_script:
                                if not self.running: break
                                if not self.execute_step(step): copy_ok = False; break
                            if copy_ok: break
                        
                        if not copy_ok: success = False
                        else:
                            my_code = self.last_captured_code
                            if not my_code: success = False
                            else:
                                with self.shared_data["lock"]:
                                    if self.is_role_a: self.shared_data["codes"][self.pair_id]["A"] = my_code
                                    else: self.shared_data["codes"][self.pair_id]["B"] = my_code

                            if success and self.running:
                                for step in input_code_script[:-1]:
                                    if not self.running: break
                                    if not self.execute_step(step): success = False; break

                                partner_code = None; wait_start = time.time()
                                partner_info = None # Lưu thông tin đối phương cục bộ
                                while time.time() - wait_start < 60 and self.running:
                                    with self.shared_data["lock"]:
                                        pair_data = self.shared_data["codes"].get(self.pair_id, {})
                                        partner_code = pair_data.get("B" if self.is_role_a else "A")
                                        partner_info = pair_data.get("acc_B" if self.is_role_a else "acc_A")
                                    if partner_code and partner_info: 
                                        self.log(f"==> ĐÃ NHẬN MÃ TỪ ĐỐI PHƯƠNG: {partner_code}")
                                        break
                                    time.sleep(3)
                                
                                if not partner_code:
                                    self.log("!! QUÁ THỜI GIAN CHỜ MÃ ĐỐI PHƯƠNG (60s). Đang khởi động lại...")
                                    self.execute_step({"action": "restart_app"})
                                    success = False
                                else:
                                    self.partner_code = partner_code
                                    # Lưu thông tin cặp để ghi report sau này (tránh bị reset khi máy kia sang acc mới)
                                    self.final_report_data = {
                                        "my_acc": self.current_account,
                                        "my_code": my_code,
                                        "partner_acc": partner_info,
                                        "partner_code": partner_code
                                    }
                                    
                                    if not self.execute_step(input_code_script[-1]): success = False
                                    if success:
                                        for step in confirm_script:
                                            if not self.running: break
                                            if not self.execute_step(step): success = False; break
                    
                    # --- KẾT THÚC VÀ BÁO CÁO ---
                    if self.running:
                        if success or self.current_account.get("success"):
                            self.current_account["success"] = True
                            if self.use_external_codes:
                                self.report_stats_func(True, target_code, True)
                            elif self.is_role_a and hasattr(self, 'final_report_data'):
                                # Sử dụng dữ liệu đã chốt từ lúc bắt tay để ghi file
                                d = self.final_report_data
                                a_acc, a_code = d["my_acc"], d["my_code"]
                                b_acc, b_code = d["partner_acc"], d["partner_code"]
                                
                                a_info = f"{a_acc['tk']}|{a_acc['mk']}|{a_code}"
                                b_info = f"{b_acc['tk']}|{b_acc['mk']}|{b_code}"
                                self.report_stats_func(True, f"Cặp {self.pair_id+1}: {a_info} <-> {b_info}")
                            break # THÀNH CÔNG - Thoát vòng lặp retry
                        else:
                            # THẤT BẠI - Ghi log và để vòng lặp while tiếp tục thử lại chính acc này
                            self.log(f"!! Lỗi thực thi, đang thử lại chính tài khoản: {self.current_account['tk']}")
                            time.sleep(2) # Đợi một chút trước khi thử lại
                        
                    # Giải phóng bộ nhớ sau mỗi acc/cặp
                    gc.collect()
        except Exception as e:
            self.log(f"!! LỖI HỆ THỐNG (Thread Crash): {str(e)}")
            import traceback
            traceback.print_exc()
                
            gc.collect()

        self.log(">> LUỒNG ĐÃ DỪNG HOÀN TOÀN.")
        self.update_status("Đã dừng")
        self.running = False
        
       
class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaLQTool(BoxPhone) - Code Pairing")
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
            "codes": {}, 
            "lock": threading.Lock(),
            "external_codes": [],
            "ext_lock": threading.Lock()
        }
        self.adb_path = self.find_adb()
        self.device_map = {}
        self.device_cards = {}
        
        try:
            self.logo_img = ctk.CTkImage(Image.open(resource_path("logo_cs_cheo.png")), size=(64, 64))
            self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
            self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))
        except:
            self.logo_img = self.start_icon = self.stop_icon = None
        
        self.setup_layout()
        self.scan_devices()
        
        # Redirect stdout và stderr về log UI
        sys.stdout = StdoutRedirector(self.add_log)
        sys.stderr = StdoutRedirector(self.add_log)

    def setup_layout(self):
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=NAV_COLOR); self.sidebar.pack(side="left", fill="y")
        if self.logo_img: ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=20)
        ctk.CTkLabel(self.sidebar, text="PAIRING EDITION", font=("Arial", 16, "bold"), text_color=ACCENT_GREEN).pack()
        
        self.account_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10); self.account_card.pack(padx=15, pady=10, fill="x")
        ctk.CTkButton(self.account_card, text="NẠP FILE ACC", command=self.load_accounts, fg_color="#f59e0b", hover_color="#d97706", text_color="#fff", font=("Segoe UI", 11, "bold"), height=32).pack(pady=(10, 5), padx=10, fill="x")
        ctk.CTkButton(self.account_card, text="NẠP FILE MÃ MỜI", command=self.load_external_codes, fg_color="#0ea5e9", hover_color="#0284c7", text_color="#fff", font=("Segoe UI", 11, "bold"), height=32).pack(pady=(5, 10), padx=10, fill="x")

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

        # Thẻ Mã Mời
        self.card_code = ctk.CTkFrame(stats_container, fg_color=CARD_COLOR, height=80, corner_radius=12, border_width=1, border_color="#333")
        self.card_code.pack(side="left", fill="both", expand=True, padx=5)
        ctk.CTkLabel(self.card_code, text="MÃ MỜI CÒN LẠI", font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(pady=(10, 0))
        self.code_count_val = ctk.CTkLabel(self.card_code, text="0", font=("Segoe UI", 28, "bold"), text_color="#fbbf24")
        self.code_count_val.pack(pady=(0, 5))

        # Thẻ Thành Công
        self.card_success = ctk.CTkFrame(stats_container, fg_color=CARD_COLOR, height=80, corner_radius=12, border_width=1, border_color="#333")
        self.card_success.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ctk.CTkLabel(self.card_success, text="CẶP THÀNH CÔNG", font=("Segoe UI", 10, "bold"), text_color="#94a3b8").pack(pady=(10, 0))
        self.success_val = ctk.CTkLabel(self.card_success, text="0", font=("Segoe UI", 28, "bold"), text_color="#34d399")
        self.success_val.pack(pady=(0, 5))

        # --- DEVICE LIST SECTION ---
        inst_header = ctk.CTkFrame(self.main_content, fg_color="transparent")
        inst_header.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(inst_header, text="DANH SÁCH THIẾT BỊ HOẠT ĐỘNG", font=("Segoe UI", 13, "bold"), text_color=ACCENT_GREEN).pack(side="left")
        self.btn_refresh = ctk.CTkButton(inst_header, text="Làm Mới ADB", command=self.scan_devices, width=100, height=28, font=("Segoe UI", 11, "bold"), fg_color="#334155", hover_color="#475569")
        self.btn_refresh.pack(side="right")
        
        self.device_list_frame = ctk.CTkScrollableFrame(self.main_content, height=220, fg_color="#111", corner_radius=12, border_width=1, border_color="#222")
        self.device_list_frame.pack(fill="x", pady=10)
        
        # --- LOG SYSTEM ---
        log_header = ctk.CTkFrame(self.main_content, fg_color="transparent")
        log_header.pack(fill="x", pady=(5, 0))
        ctk.CTkLabel(log_header, text="HỆ THỐNG GIÁM SÁT REAL-TIME", font=("Segoe UI", 11, "bold"), text_color="#64748b").pack(side="left")
        
        self.log_txt = ctk.CTkTextbox(self.main_content, height=180, fg_color="#09090b", text_color="#e2e8f0", font=("Consolas", 11), border_width=1, border_color="#222")
        self.log_txt.pack(fill="both", expand=True, pady=(5, 0))
        self.load_adb_config()

    def find_adb(self):
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
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        # Chia serials thành từng nhóm 2 (Cặp)
        for i in range(0, len(serials), 2):
            team_serials = serials[i:i+2]
            team_num = (i // 2) + 1
            
            team_card = ctk.CTkFrame(self.device_list_frame, fg_color="#18181b", corner_radius=12, border_width=1, border_color="#27272a")
            team_card.pack(fill="x", pady=6, padx=10)
            
            header = ctk.CTkFrame(team_card, fg_color="transparent", height=32)
            header.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(header, text=f"NHÓM CẶP #{team_num:02d}", font=("Segoe UI", 11, "bold"), text_color="#38bdf8").pack(side="left")
            
            btn_stop_all = ctk.CTkButton(header, text="DỪNG CẶP", image=self.stop_icon, width=90, height=26, fg_color="#3f3f46", hover_color="#52525b", font=("Segoe UI", 10, "bold"), command=lambda ts=team_serials: self.stop_team(ts))
            btn_stop_all.pack(side="right", padx=2)
            btn_play_all = ctk.CTkButton(header, text="CHẠY CẶP", image=self.start_icon, width=90, height=26, fg_color="#10b981", hover_color="#059669", font=("Segoe UI", 10, "bold"), command=lambda ts=team_serials: self.start_team(ts))
            btn_play_all.pack(side="right", padx=2)

            device_grid = ctk.CTkFrame(team_card, fg_color="transparent")
            device_grid.pack(fill="x", padx=8, pady=(0, 8))
            
            for idx_in_team, s in enumerate(team_serials):
                global_idx = i + idx_in_team
                self.device_map[s] = global_idx
                is_role_a = (idx_in_team == 0)
                
                dev_box = ctk.CTkFrame(device_grid, fg_color="#09090b", corner_radius=10, border_width=1, border_color="#1e1e1e")
                dev_box.pack(side="left", padx=4, fill="x", expand=True)
                
                color = "#38bdf8" if is_role_a else "#fbbf24"
                lbl_role = "MÁY A (Chủ)" if is_role_a else "MÁY B (Khách)"
                
                # Header máy (Role + Serial)
                top_row = ctk.CTkFrame(dev_box, fg_color="transparent")
                top_row.pack(fill="x", padx=8, pady=(6, 2))
                ctk.CTkLabel(top_row, text=lbl_role, font=("Segoe UI", 10, "bold"), text_color=color).pack(side="left")
                ctk.CTkLabel(top_row, text=f"[{s}]", font=("Consolas", 9), text_color="#4b5563").pack(side="left", padx=5)
                
                # Bottom row (Status + Buttons)
                bot_row = ctk.CTkFrame(dev_box, fg_color="transparent")
                bot_row.pack(fill="x", padx=8, pady=(0, 6))
                
                status_lbl = ctk.CTkLabel(bot_row, text="Sẵn sàng", font=("Segoe UI", 10), text_color="#64748b")
                status_lbl.pack(side="left")
                
                b_stop = ctk.CTkButton(bot_row, text="", image=self.stop_icon, width=24, height=24, fg_color="#27272a", hover_color="#ef4444", command=lambda sn=s: self.stop_single_device(sn))
                b_stop.pack(side="right", padx=2)
                b_start = ctk.CTkButton(bot_row, text="", image=self.start_icon, width=24, height=24, fg_color="#27272a", hover_color="#10b981", command=lambda sn=s: self.start_single_device(sn))
                b_start.pack(side="right", padx=2)
                
                self.device_cards[s] = {"status": status_lbl, "start_btn": b_start, "stop_btn": b_stop}

        self.btn_refresh.configure(state="normal", text="Làm Mới")
        if not serials: ctk.CTkLabel(self.device_list_frame, text="Không tìm thấy thiết bị nào.", text_color="#888").pack(pady=20)

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
        self.total_accounts_loaded = len(self.accounts_data)
        self.add_log(f"Đã nạp {self.total_accounts_loaded} acc.")
        self.update_all_ui()

    def load_external_codes(self):
        p = fd.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not p: return
        self.ext_codes_file_path = p
        codes = []
        with open(p, 'r', encoding='utf-8') as f:
            for l in f:
                l = l.strip()
                if not l: continue
                parts = l.split('|')
                code = parts[0]
                count = 1
                if len(parts) >= 2:
                    try: count = int(parts[1])
                    except: count = 1
                codes.append({"code": code, "count": count})
        
        with self.shared_data["ext_lock"]:
            self.shared_data["external_codes"] = codes
        
        self.add_log(f"Đã nạp {len(codes)} loại mã mời từ file.")
        self.update_all_ui()

    def start_all(self):
        if not self.accounts_data: 
            self.add_log("Vui lòng nạp file tài khoản trước.")
            return
            
        # Lấy số lượng tài khoản và mã mời để tính toán giới hạn tab
        total_accounts = len(self.accounts_data)
        with self.shared_data["ext_lock"]:
            total_codes = sum(item["count"] for item in self.shared_data.get("external_codes", []))
            
        # Xác định giới hạn tab (máy) chạy đồng thời theo yêu cầu: cái nào ít hơn thì chạy cái đó
        if total_codes > 0:
            limit = min(total_accounts, total_codes)
            self.add_log(f"CHẠY TẤT CẢ: Giới hạn {limit} tab (Min: {total_accounts} acc, {total_codes} mã)")
        else:
            limit = total_accounts
            self.add_log(f"CHẠY TẤT CẢ: Giới hạn {limit} tab theo số tài khoản ({total_accounts} acc)")

        count = 0
        # Sắp xếp danh sách serial để khởi động thiết bị theo thứ tự ổn định
        serials = sorted(self.device_map.keys())
        for s in serials:
            if count >= limit:
                break
            self.start_single_device(s)
            count += 1

    def stop_all(self):
        for w in self.active_workers:
            w.running = False
        for s in self.device_cards:
            self.device_cards[s]["status"].configure(text="Stopping...", text_color="#F87171")
        self.add_log("Đã gửi lệnh dừng tới tất cả thiết bị.")

    def start_single_device(self, serial):
        # Dọn dẹp các worker cũ đã chết
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

    def save_input_files(self):
        # Cập nhật lại file Account (Xóa những acc đã success)
        if self.account_file_path:
            with FILE_LOCK:
                try:
                    remaining_accs = [acc for acc in self.accounts_data if not acc.get("success")]
                    with open(self.account_file_path, 'w', encoding='utf-8') as f:
                        for acc in remaining_accs:
                            f.write(f"{acc['tk']}|{acc['mk']}\n")
                except: pass

        # Cập nhật lại file Mã mời (Xóa hoặc giảm lượt dùng)
        if hasattr(self, 'ext_codes_file_path') and self.ext_codes_file_path:
            with self.shared_data["ext_lock"]:
                try:
                    codes = self.shared_data.get("external_codes", [])
                    with open(self.ext_codes_file_path, 'w', encoding='utf-8') as f:
                        for item in codes:
                            if item["count"] > 0:
                                f.write(f"{item['code']}|{item['count']}\n")
                except: pass

    def report_stats(self, success, info, is_code=False):
        if success: self.success_count += 1
        else: self.failure_count += 1
        
        if is_code:
            # Aggregate and rewrite for external codes
            with self.shared_data["ext_lock"]:
                if "success_map" not in self.shared_data:
                    self.shared_data["success_map"] = {}
                
                code = info
                self.shared_data["success_map"][code] = self.shared_data["success_map"].get(code, 0) + 1
                
                try:
                    with open("SUCCESS_CODES.txt", "w", encoding="utf-8") as f:
                        for c, count in self.shared_data["success_map"].items():
                            f.write(f"{c}|{count}\n")
                except Exception as e:
                    self.add_log(f"LỖI ghi file SUCCESS_CODES.txt: {e}")
        else:
            fn = "SUCCESS_PAIRS.txt" if success else "FAILED_PAIRS.txt"
            status_text = "THÀNH CÔNG" if success else "THẤT BẠI"
            self.add_log(f"[{status_text}] {info}")
            with FILE_LOCK:
                with open(fn, "a", encoding="utf-8") as f: f.write(f"{info}\n")
        
        if success:
            self.save_input_files()

        self.after(0, self.update_all_ui)
        gc.collect() # Giải phóng bộ nhớ sau mỗi lần báo cáo

    def update_all_ui(self):
        self.success_val.configure(text=str(self.success_count))
        self.acc_count_val.configure(text=str(self.total_accounts_loaded))
        with self.shared_data["ext_lock"]:
            total_remaining = sum(item["count"] for item in self.shared_data.get("external_codes", []))
        self.code_count_val.configure(text=str(total_remaining))

    def add_log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        # Chỉ cho phép log hệ thống (nạp file) hoặc log đã được lọc từ Instance
        allowed_system = ["Đã nạp", "CHẠY TẤT CẢ", "Đã bắt chạy", "ADB"]
        is_allowed = any(s in text for s in allowed_system) or ">> START" in text or "[" in text
        
        if is_allowed:
            full_text = f"[{now}] {text}"
            try: self.after(0, lambda: self._safe_append_log(full_text))
            except: pass

    def _safe_append_log(self, msg):
        try:
            self.log_txt.insert("end", msg + "\n")
            
            # Giới hạn 100 dòng log để tránh tràn bộ nhớ gây văng app
            current_index = self.log_txt.index("end-1c")
            num_lines = int(current_index.split(".")[0])
            if num_lines > 100:
                self.log_txt.delete("1.0", f"{num_lines - 100}.0")
                
            self.log_txt.see("end")
        except: pass

if __name__ == "__main__":
    app = MultiPremiumApp()
    app.mainloop()

# pyinstaller --noconfirm --onefile --windowed --name "MegaLQCSCheo" --add-data "images;images" --add-data "logo_cs_cheo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool_cs_cheo.py

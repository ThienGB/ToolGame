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

    def log(self, msg):
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
                subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
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
        cmd = [self.adb_path, "-s", self.device_id] + args
        try:
            return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, 1, b'', b'')

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
        res = subprocess.run(cmd, capture_output=True, text=False, creationflags=subprocess.CREATE_NO_WINDOW)
        
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
            res_service = subprocess.run(cmd_service, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            # Kết quả service call cần parse rất phức tạp (HEX), nên đây chỉ là phương án dự phòng
        except: pass

        # 3. Thất bại
        return ""



    def execute_step(self, step):
        if not self.running: return False
        action = step.get("action")
        target_info = step.get("target") or step.get("target1", "")
        self.log(f"==> Bước: {action} {f'({target_info})' if target_info else ''}")
        self.last_step_time = time.time()
        res = True
        
        if action == "click_image":
            res = bool(self.click_image_logic(step))
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
            self.log("Đang khởi động Clipper Service...")
            self.call_adb(["shell", "am", "start-foreground-service", f"{pkg}/.ClipboardService"])
            # Xóa file cũ để tránh nhận nhầm mã cũ
            self.call_adb(["shell", "rm", "-f", f"/sdcard/Android/data/{pkg}/files/clip.txt"])
            res = True
        elif action == "get_code":
            # Lấy mã hoàn toàn từ Clipboard Helper
            self.last_captured_code = self.get_clipboard()
            
            if self.last_captured_code:
                self.log(f"==> KẾT QUẢ LẤY MÃ: {self.last_captured_code}")
            else:
                self.log("!! KẾT QUẢ LẤY MÃ: Thất bại (Vui lòng kiểm tra APK Helper)")
            res = (self.last_captured_code != "")
        elif action == "input_partner_code":
            self.call_adb(["shell", "input", "keyevent"] + ["67"] * 25) # Xóa cũ
            self.input_text_robust(self.partner_code)
            res = True
        elif action == "cases":
            res = self.cases_logic(step)
            if not res and "timeout_then" in step:
                for sub_step in step.get("timeout_then", []):
                    if not self.execute_step(sub_step):
                        return False
                return True # Đã xử lý bằng timeout_then, coi như bước này thành công
            return res # Trả về True nếu khớp case, False nếu timeout mà không có timeout_then
        elif action == "restart_app":
            app = step.get("app", "com.garena.game.kgvn")
            self.log(f"!! PHÁT HIỆN LỖI: Đóng game và khởi động lại {app}...")
            self.call_adb(["shell", "am", "force-stop", app])
            time.sleep(2)
            self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
            self.log("Đợi game khởi động lại (20s)...")
            time.sleep(20)
            return False
        elif action == "handle_maintenance":
            app = step.get("app", "com.garena.game.kgvn")
            self.log("!! PHÁT HIỆN BẢO TRÌ: Đang khởi động lại và sẽ bỏ qua phần đăng nhập...")
            self.skip_login_for_this_acc = True
            self.call_adb(["shell", "am", "force-stop", app])
            time.sleep(2)
            self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
            self.log("Đợi game khởi động lại (20s)...")
            time.sleep(20)
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
                        self.log(f"==> CLICK OK: {os.path.basename(t_path)} ({mv:.2f})")
                        return t_path
            time.sleep(1)
        
        self.log(f"!! Timeout: Không thấy ảnh. Cao nhất: {best_match['name']} ({best_match['val']:.2f})")
        return None

    def cases_logic(self, step):
        cases = step.get("cases", [])
        if not cases: return True
        timeout = step.get("timeout", 10)
        confidence = step.get("confidence", 0.8)
        
        start_time = time.time()
        while time.time() - start_time < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None:
                time.sleep(1); continue
            
            for case in cases:
                triggers = []
                if case.get("trigger"): triggers.append(case.get("trigger"))
                idx = 1
                while f"trigger{idx}" in case:
                    triggers.append(case.get(f"trigger{idx}")); idx += 1
                
                case_conf = case.get("confidence", confidence)
                sub_script = case.get("script", [])
                
                for t_path in triggers:
                    real_path = resource_path(t_path)
                    if not os.path.exists(real_path): continue
                    
                    t_img = cv2.imread(real_path, cv2.IMREAD_GRAYSCALE)
                    if t_img is None: continue
                    
                    scr_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                    # Tỉ lệ 1:1
                    t_scaled = t_img
                    
                    if t_scaled.shape[0] > scr_gray.shape[0] or t_scaled.shape[1] > scr_gray.shape[1]:
                        continue
                    res = cv2.matchTemplate(scr_gray, t_scaled, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, _ = cv2.minMaxLoc(res)
                    if mv >= case_conf:
                        self.log(f"-> PHÁT HIỆN: {os.path.basename(t_path)}")
                        for s_step in sub_script:
                            if not self.running: break
                            self.execute_step(s_step)
                        return True 
            time.sleep(1)
        return False

    def search_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        use_color = step.get("use_color", False)
        real_path = resource_path(target)
        if not os.path.exists(real_path): return False
        
        read_mode = cv2.IMREAD_COLOR if use_color else cv2.IMREAD_GRAYSCALE
        t_img = cv2.imread(real_path, read_mode)
        
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                if not use_color: compare_screen = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                else: compare_screen = screen

                # Tỉ lệ 1:1
                t_scaled = t_img

                if t_scaled.shape[0] > compare_screen.shape[0] or t_scaled.shape[1] > compare_screen.shape[1]:
                    continue
                res = cv2.matchTemplate(compare_screen, t_scaled, cv2.TM_CCOEFF_NORMED)
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

    def verify_or_restart_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 15)
        app = step.get("app", "com.garena.game.kgvn")
        
        found = self.search_logic({"target": target, "timeout": timeout, "confidence": step.get("confidence", 0.7)})
        if found: 
            return True
        
        self.log(f"!! KHÔNG THẤY {target}. TIẾN HÀNH KHỞI ĐỘNG LẠI {app}!")
        self.call_adb(["shell", "am", "force-stop", app])
        time.sleep(2)
        self.call_adb(["shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1"])
        
        self.log("Đợi game khởi động lại và chạy restart_script...")
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
            {"action": "click_image_if", "target": "images/login_garena.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/login_garena.png", "timeout": 3, "confidence": 0.7, "login_step": True},
            {"action": "click_image", "target1": "images/username.png","target2": "images/account_input.png", "target3": "images/account.jpg", "target4": "images/account_input_note8.jpg", "timeout": 60, "confidence": 0.7, "login_step": True},
            {"action": "input_account", "login_step": True},
            {"action": "click_image", "target1": "images/tiep_theo.jpg", "target2": "images/tiep_theo1.jpg", "timeout": 60, "confidence": 0.7, "login_step": True},
            {"action": "input_password", "login_step": True},
            {"action": "wait", "timeout": 2, "login_step": True},
            {"action": "click_image", "target1": "images/xong.jpg", "target2": "images/xong1.jpg", "timeout": 30, "confidence": 0.7, "login_step": True},
            {"action": "wait", "timeout": 5, "login_step": True},
            {"action": "click_image_if", "target1": "images/ok2.png", "target2": "images/ok_dang_nhap.jpg", "timeout": 4, "confidence": 0.7, "login_step": True},
            {"action": "click_image_if", "target1": "images/ok2.png", "target2": "images/ok_dang_nhap.jpg", "timeout": 2, "confidence": 0.7, "login_step": True},
            {"action": "wait", "timeout": 5, "login_step": True},
            {"action": "click_image_if", "target1": "images/login.png", "target2": "images/login_now.png", "target3": "images/dang_nhap1.jpg", "timeout": 7, "confidence": 0.7, "login_step": True},
            {"action": "click_image_if", "target1": "images/loi_mang.jpg", "target2": "images/sai_pass.jpg", "timeout": 5, "confidence": 0.8, "login_step": True, "then": [
                {"action": "clear_android_data", "package": "com.garena.gaslite"},
                {"action": "restart_app"}]
            },
            
            {"action": "click_image_if", "target": "images/batdau.png", "timeout": 6, "confidence": 0.7},
            # {"action": "click_image_if", "target1": "images/skip.png", "target2": "images/dang_ky_sau.jpg", "timeout": 15, "confidence": 0.7},
            # {
            #     "action": "cases",
            #     "timeout" : 120,
            #     "timeout_then": [{"action": "handle_maintenance"}],
            #     "cases": [
            #         {
            #             "trigger": "images/an_de_tro_lai.jpg",
            #             "confidence": 0.7,
            #             "script": [
            #                 {"action": "click_image_if", "target": "images/an_de_tro_lai.jpg", "confidence": 0.7},
            #                 {"action": "wait", "timeout": 2},
            #                 {"action": "click_image_if", "target": "images/an_de_tro_lai.jpg", "confidence": 0.7, "timeout": 5},
            #                 {"action": "wait", "timeout": 2},
            #                 {"action": "click_image_if", "target": "images/an_de_tro_lai.jpg", "confidence": 0.7, "timeout": 5},
            #                 {"action": "click_image_if", "target": "images/an_de_tro_lai.jpg", "confidence": 0.7, "timeout": 5},
            #                 {"action": "click_image_if", "target": "images/x_start.jpg", "confidence": 0.7},
            #                 {"action": "click_image_if", "target": "images/x_start1.jpg", "confidence": 0.7},
            #                 {"action": "click_image_if", "target": "images/x_start1.jpg", "confidence": 0.7}
            #             ]
            #         },
            #         {
            #             "trigger": "images/x_start.jpg",
            #             "confidence": 0.7,
            #             "script": [
            #                 {"action": "click_image_if", "target": "images/x_start.jpg", "confidence": 0.7, "timeout": 5},
            #                 {"action": "click_image_if", "target": "images/x_start.jpg", "confidence": 0.7, "timeout": 2},
            #                 {"action": "click_image_if", "target": "images/x_start1.jpg", "confidence": 0.7, "timeout": 2},

            #             ]
            #         },
            #         {
            #             "trigger": "images/pvp.png",
            #             "confidence": 0.7,
            #             "script": []
            #         }
            #     ]
            # },
            # {"action": "press_esc", "wait": 2},
            # {"action": "click_image_if", "target": "images/x_start.jpg", "confidence": 0.7, "timeout": 3},
            # {"action": "click_image_if", "target": "images/x_start1.jpg", "confidence": 0.7, "timeout": 2},
            # {"action": "click_image_if", "target": "images/x_start2.jpg", "confidence": 0.7, "timeout": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
        ]
        
        restart_script = [
            {"action": "wait", "timeout": 20}, # Đợi game khởi động
            {"action": "click_image_if", "target": "images/login_garena.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/x_start.jpg", "timeout": 4, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/x_start1.jpg", "timeout": 4, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/x_start.jpg", "timeout": 4, "confidence": 0.7},
            {"action": "press_esc", "wait": 3},
        ]
        
        copy_script = [
            {
                "action": "cases",
                "timeout" : 120,
                "timeout_then": [{"action": "handle_maintenance"}],
                "cases": [
                    {
                        "trigger": "images/su_kien.jpg",
                        "confidence": 0.7,
                        "script": []
                    }
                ]
            },
            {"action": "click_image", "target": "images/su_kien.jpg", "timeout": 5, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/buoc_nhay_chung_suc.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "verify_or_restart", "target": "images/nhap_ma_moi.jpg", "timeout": 15, "script": restart_script},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images/invite_friend.jpg", "timeout": 5, "confidence": 0.7},
            {"action": "click_image", "target": "images/sao_chep_ma.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image", "target": "images/sao_chep_ma.jpg", "timeout": 5, "confidence": 0.7},
            {"action": "get_code", "timeout": 10}, # Hàm get_code bây giờ sẽ ưu tiên Clipboard
            {"action": "press_esc", "wait": 2},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images/nhap_ma_moi.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/nhap_ma_moi.jpg", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/input_gift_code.jpg", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target1": "images/input_gift_code.jpg", "target2": "images/input_gift_code1.jpg", "timeout": 2, "confidence": 0.7},
        ]
        
        input_code_script = [
            {"action": "input_partner_code"},
        ]
        
        confirm_script = [
            {"action": "click_image_if", "target": "images/ok_cs.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/xac_nhan_chung_suc.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/xac_nhan_chung_suc1.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/tiep_tuc_cs.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/x_cs2.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/tiep_tuc_cs.jpg", "timeout": 3, "confidence": 0.7},
            {"action": "click_image", "target": "images/back_sk1.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/back_sk1.jpg", "timeout": 2, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/back_sk1.jpg", "timeout": 2, "confidence": 0.7},
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target1": "images/setting.jpg", "target2": "images/setting1.jpg", "timeout": 10, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/logout.jpg", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/ok.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
        ]
        
        while self.running:
            self.current_account = None
            with FILE_LOCK:
                for acc in self.accounts_list:
                    if not acc.get("used"):
                        acc["used"] = True; self.current_account = acc
                        self.update_ui_func(); break
            if not self.current_account: break
            self.log(f">> START {self.role_name}: {self.current_account['tk']}")
            
            # --- DỌN DẸP VÀ KHỞI ĐỘNG CLIPPER SERVICE CHO VÒNG MỚI ---
            self.last_captured_code = None
            self.skip_login_for_this_acc = False
            self.skip_all_retries = False
            pkg = "com.example.clipper"
            # Bật Service để hiện Nút nổi (Pill)
            self.call_adb(["shell", "am", "start-foreground-service", f"{pkg}/.ClipboardService"])
            # Xóa mã cũ
            path_in_android = f"/sdcard/Android/data/{pkg}/files/clip.txt"
            self.call_adb(["shell", "rm", "-f", path_in_android])

            # --- THỰC HIỆN ĐĂNG NHẬP TRƯỚC ---
            self.update_status("Đang Login...")
            success_login = False
            for retry_login in range(3):
                success_login = True
                for step in login_script:
                    if not self.running: break
                    
                    # Nếu đang trong chế độ skip login và bước này là login_step thì bỏ qua
                    if self.skip_login_for_this_acc and step.get("login_step"):
                        continue
                        
                    if not self.execute_step(step):
                        success_login = False; break
                if success_login or not self.running or self.skip_all_retries: break
                self.log(f"!! Login thất bại (vòng {retry_login+1}/3). Đang bắt đầu lại từ đầu cho account này...")
                    
            if not success_login or not self.running:
                self.report_stats_func(False, f"{self.current_account['tk']}|{self.current_account['mk']}")
                continue
            
            # --- KHỞI TẠO ĐỒNG BỘ CẶP ---
            with self.shared_data["lock"]:
                if self.pair_id not in self.shared_data["codes"]:
                    self.shared_data["codes"][self.pair_id] = {"A": None, "B": None, "acc_A": None, "acc_B": None}
                # Lưu acc đang chạy vào nhóm
                if self.is_role_a: self.shared_data["codes"][self.pair_id]["acc_A"] = self.current_account
                else: self.shared_data["codes"][self.pair_id]["acc_B"] = self.current_account
            
            success = True
            
            # KỊCH BẢN COPY MÃ VÀ ĐỔI MÃ:
            # 1. Tìm và click nút LẤY MÃ
            self.update_status("Đang lấy mã...")
            
            for retry in range(2):
                copy_ok = True
                for step in copy_script:
                    if not self.running: break
                    res_step = self.execute_step(step)
                    if step.get("action") == "verify_or_restart" and not res_step:
                        copy_ok = False
                        break
                if copy_ok: 
                    break
            
            # 2. Đọc mã mới đã được lưu trong self.last_captured_code
            my_code = self.last_captured_code
            if not my_code:
                self.log("!! KHÔNG LẤY ĐƯỢC MÃ QUA CLIPBOARD. Bỏ qua.")
                success = False
            else:
                self.log(f"==> Đã lấy được mã: {my_code}")
                # Chia sẻ mã lên bộ nhớ dùng chung
                with self.shared_data["lock"]:
                    if self.is_role_a: self.shared_data["codes"][self.pair_id]["A"] = my_code
                    else: self.shared_data["codes"][self.pair_id]["B"] = my_code

            if success and self.running:
                # 3. Chủ động chuẩn bị sẵn ở màn hình nhập mã (trong lúc đợi đối phương)
                self.update_status("Đang chuẩn bị nhập mã...")
                # Chạy các bước navigation (tất cả trừ bước cuối cùng là nhập mã)
                for step in input_code_script[:-1]:
                    if not self.running: break
                    self.execute_step(step)

                # 4. Đợi mã của đối phương
                self.update_status("Đợi mã đối phương...")
                partner_code = None
                wait_start = time.time()
                while time.time() - wait_start < 120 and self.running:
                    with self.shared_data["lock"]:
                        partner_code = self.shared_data["codes"][self.pair_id]["B"] if self.is_role_a else self.shared_data["codes"][self.pair_id]["A"]
                    if partner_code: break
                    time.sleep(2)
                
                if not partner_code:
                    self.log("!! TIME OUT: Không nhận được mã từ đối phương.")
                    success = False
                else:
                    self.log(f"==> Nhận được mã đối phương: {partner_code}")
                    # 5. Điền mã và xác nhận
                    self.partner_code = partner_code
                    self.update_status("Đang nhập mã...")
                    # Chạy bước cuối cùng của input_code_script (input_partner_code)
                    self.execute_step(input_code_script[-1])
                    
                    # Click các bước xác nhận
                    for step in confirm_script:
                        if not self.running: break
                        self.execute_step(step)
            
            # --- KẾT THÚC VÀ BÁO CÁO ---
            if self.running:
                # Ghi nhận kết quả
                if success:
                    # Đợi một chút để cả 2 máy hoàn thành trước khi ghi file
                    time.sleep(5)
                    # Chỉ máy A ghi file để tránh ghi trùng (nếu cần file chung)
                    if self.is_role_a:
                        with self.shared_data["lock"]:
                            a_acc = self.shared_data["codes"][self.pair_id]["acc_A"]
                            b_acc = self.shared_data["codes"][self.pair_id]["acc_B"]
                            code_a = self.shared_data["codes"][self.pair_id]["A"]
                            code_b = self.shared_data["codes"][self.pair_id]["B"]
                        
                        a_info = f"{a_acc['tk']}|{a_acc['mk']}" if a_acc else "N/A|N/A"
                        b_info = f"{b_acc['tk']}|{b_acc['mk']}" if b_acc else "N/A|N/A"
                        self.report_stats_func(True, f"AccA: {a_info} | AccB: {b_info} | Ma_A: {code_a} | Ma_B: {code_b}")
                else:
                    self.report_stats_func(False, f"{self.current_account['tk']}|{self.current_account['mk']}")
                    
            gc.collect()

        self.update_status("Xong"); self.running = False

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
        self.shared_data = {"codes": {}, "lock": threading.Lock()}
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
        
        self.account_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR); self.account_card.pack(padx=20, pady=20, fill="x")
        ctk.CTkButton(self.account_card, text="NẠP FILE ACC", command=self.load_accounts, fg_color="#EAB308", text_color="#000").pack(pady=10, padx=10, fill="x")

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

        self.main_content = ctk.CTkFrame(self, fg_color="transparent"); self.main_content.pack(side="right", fill="both", expand=True, padx=20, pady=20)
        
        inst_header = ctk.CTkFrame(self.main_content, fg_color="transparent"); inst_header.pack(fill="x")
        ctk.CTkLabel(inst_header, text="DANH SÁCH BOXPHONE", font=("Arial", 14, "bold"), text_color=ACCENT_GREEN).pack(side="left")
        self.btn_refresh = ctk.CTkButton(inst_header, text="Làm Mới", command=self.scan_devices, width=80)
        self.btn_refresh.pack(side="right")
        
        self.device_list_frame = ctk.CTkScrollableFrame(self.main_content, height=250, fg_color=CARD_COLOR); self.device_list_frame.pack(fill="x", pady=10)
        
        self.stats_inner = ctk.CTkFrame(self.main_content, fg_color="transparent"); self.stats_inner.pack(fill="x", pady=10)
        self.success_val = ctk.CTkLabel(self.stats_inner, text="0", font=("Arial", 50, "bold"), text_color="#4ADE80"); self.success_val.pack()
        ctk.CTkLabel(self.stats_inner, text="CẶP THÀNH CÔNG", font=("Arial", 14)).pack()
        
        ctk.CTkLabel(self.main_content, text="LOG HỆ THỐNG", font=("Arial", 12, "bold"), text_color="#888").pack(pady=(10,0))
        self.log_txt = ctk.CTkTextbox(self.main_content, height=150, fg_color="#18181b", text_color="#d1d5db", font=("Consolas", 11))
        self.log_txt.pack(fill="both", expand=True, pady=10)
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
            
            team_card = ctk.CTkFrame(self.device_list_frame, fg_color="#1a1a1a", corner_radius=10, border_width=1, border_color="#333")
            team_card.pack(fill="x", pady=8, padx=10)
            
            header = ctk.CTkFrame(team_card, fg_color="transparent", height=40)
            header.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(header, text=f"PAIR {team_num}", font=("Arial", 14, "bold"), text_color=ACCENT_GREEN).pack(side="left")
            
            btn_play_all = ctk.CTkButton(header, text="START PAIR", image=self.start_icon, width=110, height=30, fg_color="#10b981", font=("Arial", 11, "bold"), command=lambda ts=team_serials: self.start_team(ts))
            btn_play_all.pack(side="right", padx=5)
            btn_stop_all = ctk.CTkButton(header, text="STOP PAIR", image=self.stop_icon, width=110, height=30, fg_color="#4b5563", font=("Arial", 11, "bold"), command=lambda ts=team_serials: self.stop_team(ts))
            btn_stop_all.pack(side="right", padx=5)

            device_grid = ctk.CTkFrame(team_card, fg_color="transparent")
            device_grid.pack(fill="x", padx=10, pady=(0, 10))
            
            for idx_in_team, s in enumerate(team_serials):
                global_idx = i + idx_in_team
                self.device_map[s] = global_idx
                is_role_a = (idx_in_team == 0)
                
                dev_box = ctk.CTkFrame(device_grid, fg_color="#252525", corner_radius=6, width=170)
                dev_box.pack(side="left", padx=4, fill="y", expand=True)
                
                color = "#3b82f6" if is_role_a else "#f59e0b"
                lbl_role = "MÁY A" if is_role_a else "MÁY B"
                ctk.CTkLabel(dev_box, text=lbl_role, font=("Arial", 10, "bold"), text_color=color).pack(pady=(5,0))
                
                ctk.CTkLabel(dev_box, text=s, font=("Arial", 9), text_color="#555").pack()
                status_lbl = ctk.CTkLabel(dev_box, text="Ready", font=("Arial", 11, "bold"), text_color="#888")
                status_lbl.pack(pady=2)
                
                btn_frame = ctk.CTkFrame(dev_box, fg_color="transparent")
                btn_frame.pack(pady=4)
                b_start = ctk.CTkButton(btn_frame, text="", image=self.start_icon, width=28, height=28, fg_color="#1f2937", command=lambda sn=s: self.start_single_device(sn))
                b_start.pack(side="left", padx=2)
                b_stop = ctk.CTkButton(btn_frame, text="", image=self.stop_icon, width=28, height=28, fg_color="#1f2937", command=lambda sn=s: self.stop_single_device(sn))
                b_stop.pack(side="left", padx=2)
                
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
        for w in self.active_workers:
            if w.device_id == serial and w.running: return

        def update_single_status():
             if serial in self.device_cards:
                 for w in self.active_workers:
                     if w.device_id == serial:
                         self.device_cards[serial]["status"].configure(text=w.status, text_color="#4ADE80" if not w.is_lagging else "#FB7185")
                         break
             self.update_all_ui()

        worker = AutoClickerInstance(serial, self.adb_path, self.add_log, update_single_status, self.report_stats)
        self.active_workers.append(worker)
        threading.Thread(target=worker.run, args=(self.accounts_data, self.device_map[serial], self.shared_data), daemon=True).start()
        self.add_log(f"Đã bắt chạy thiết bị: {serial}")

    def stop_single_device(self, serial):
        for w in self.active_workers[:]:
            if w.device_id == serial:
                w.running = False
                self.active_workers.remove(w)
        if serial in self.device_cards:
            self.device_cards[serial]["status"].configure(text="Stopped", text_color="#888")

    def report_stats(self, success, info):
        if success: self.success_count += 1
        else: self.failure_count += 1
        fn = "SUCCESS_PAIRS.txt" if success else "FAILED_PAIRS.txt"
        with FILE_LOCK:
            with open(fn, "a", encoding="utf-8") as f: f.write(f"{info}\n")
        self.after(0, self.update_all_ui)

    def update_all_ui(self):
        self.success_val.configure(text=str(self.success_count))

    def add_log(self, text):
        now = datetime.now().strftime("%H:%M:%S")
        full_text = f"[{now}] {text}"
        try: self.after(0, lambda: self._safe_append_log(full_text))
        except: pass

    def _safe_append_log(self, msg):
        try:
            self.log_txt.insert("end", msg + "\n")
            self.log_txt.see("end")
        except: pass

if __name__ == "__main__":
    app = MultiPremiumApp()
    app.mainloop()

# pyinstaller --noconfirm --onefile --windowed --name "MegaLQCSCheo" --add-data "images;images" --add-data "logo_cs_cheo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool_cs_cheo.py

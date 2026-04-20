# -*- coding: utf-8 -*-

import json
import time
import os
import subprocess
import threading
import random
import string
import re
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

# --- Fix WinError 1114 for torch/easyocr in PyInstaller ---
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

if getattr(sys, 'frozen', False):
    import os
    import sys
    _meipass = getattr(sys, '_MEIPASS', os.path.abspath("."))
    torch_lib = os.path.join(_meipass, 'torch', 'lib')
    if os.path.exists(torch_lib):
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(torch_lib)
                os.add_dll_directory(_meipass)
            except:
                pass
        os.environ['PATH'] = torch_lib + os.pathsep + _meipass + os.pathsep + os.environ.get('PATH', '')

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
        self.script = []
        self.current_account = None
        self.modes = {}
        self.accounts_processed = 0
        self.restart_threshold = 10 

    def log(self, msg):
        self.log_func(f"[{self.device_id}] {msg}")

    def update_status(self, status, is_lagging=False):
        self.status = status
        self.is_lagging = is_lagging
        self.update_ui_func()

    def escape_adb_text(self, text):
        if not text: return ""
        chars_to_escape = ['\\', '"', "'", '&', '>', '<', '|', ';', '(', ')', '*', '?', '$', '!', '#', '%', '{', '}', '~', '[', ']', '^']
        escaped_text = ""
        for char in text:
            if char == ' ': escaped_text += "%s"
            elif char in chars_to_escape: escaped_text += f"\\{char}"
            else: escaped_text += char
        return escaped_text

    def call_adb(self, args):
        cmd = [self.adb_path, "-s", self.device_id] + args
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self):
        try:
            # Sử dụng exec-out để tránh lỗi ký tự xuống dòng trên Windows cho thiết bị thật
            cmd = [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"]
            process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            
            if process.returncode != 0:
                # Nếu exec-out lỗi, thử lại bằng shell (dành cho adb cực cũ)
                cmd = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
                process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                image_bytes = process.stdout.replace(b"\r\n", b"\n")
            else:
                image_bytes = process.stdout

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


    def restart_device(self):
        self.log("BoxPhone: Đang khởi động lại thiết bị (Reboot)...")
        self.call_adb(["reboot"])
        self.update_status("Rebooting")
        time.sleep(15)
        start_wait = time.time()
        while time.time() - start_wait < 90:
             if not self.running: return False
             res_adb = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
             if self.device_id in res_adb.stdout and "device" in res_adb.stdout and "offline" not in res_adb.stdout:
                 res_boot = self.call_adb(["shell", "getprop", "sys.boot_completed"])
                 if b"1" in res_boot.stdout:
                     self.log("Thiết bị sẵn sàng.")
                     time.sleep(5)
                     return True
             time.sleep(5)
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
        elif action == "wait_for_players":
            res = self.wait_for_players_logic(step)
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

        target_imgs = []
        for t_path in targets:
            real_path = resource_path(t_path)
            if os.path.exists(real_path):
                img = cv2.imread(real_path, cv2.IMREAD_GRAYSCALE)
                if img is not None: target_imgs.append((t_path, img))
            else: self.log(f"Thiếu ảnh mẫu: {t_path}")

        start = time.time()
        best_match = {"val": 0, "name": ""}
        last_screen = None
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                last_screen = screen
                h_screen, w_screen = screen.shape[:2]
                scale = h_screen / BASE_HEIGHT # TỈ LỆ CHUẨN: Tính theo chiều dọc

                screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                
                for t_path, t_img in target_imgs:
                    # Thử 3 tỉ lệ nhỏ xung quanh scale chuẩn để bù đắp sai lệch aspect ratio
                    for s_mod in [1.0, 0.98, 1.02]:
                        curr_scale = scale * s_mod
                        # Chọn phép nội suy phù hợp: CUBIC cho phóng to, AREA cho thu nhỏ
                        interp = cv2.INTER_CUBIC if curr_scale > 1.0 else cv2.INTER_AREA
                        
                        tw, th = int(t_img.shape[1]*curr_scale), int(t_img.shape[0]*curr_scale)
                        t_scaled = cv2.resize(t_img, (tw, th), interpolation=interp)

                        res = cv2.matchTemplate(screen_gray, t_scaled, cv2.TM_CCOEFF_NORMED)
                        _, mv, _, ml = cv2.minMaxLoc(res)
                        
                        if mv > best_match["val"]:
                            best_match = {"val": mv, "name": os.path.basename(t_path)}
                            
                        if mv >= confidence:
                            th_s, tw_s = t_scaled.shape[:2]
                            self.call_adb(["shell", "input", "tap", str(ml[0]+tw_s//2), str(ml[1]+th_s//2)])
                            self.log(f"==> CLICK OK: {os.path.basename(t_path)} ({mv:.2f} @ {curr_scale:.2f}x)")
                            return True

            time.sleep(1)
        
        if last_screen is not None:
            cv2.imwrite("debug_fail.png", last_screen)
            self.log("!! Đã lưu ảnh chụp màn hình lỗi vào: debug_fail.png")
            
        self.log(f"!! Timeout: Không thấy ảnh. Cao nhất: {best_match['name']} ({best_match['val']:.2f})")
        return False



    def search_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        real_path = resource_path(target)
        if not os.path.exists(real_path): return False
        t_img = cv2.imread(real_path, cv2.IMREAD_GRAYSCALE)
        
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                h_screen, w_screen = screen.shape[:2]
                scale = h_screen / BASE_HEIGHT

                screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
                if abs(scale - 1.0) > 0.01:
                    t_scaled = cv2.resize(t_img, (int(t_img.shape[1]*scale), int(t_img.shape[0]*scale)), interpolation=cv2.INTER_AREA)
                else: t_scaled = t_img

                res = cv2.matchTemplate(screen_gray, t_scaled, cv2.TM_CCOEFF_NORMED)
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
        self.call_adb(["shell", "input", "text", self.escape_adb_text(step.get("content", ""))])
        return True

    def input_account_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("tk", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
        self.call_adb(["shell", "input", "text", self.escape_adb_text(content)])
        return True

    def input_password_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("mk", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
        self.call_adb(["shell", "input", "text", self.escape_adb_text(content)])
        return True

    def get_room_id_logic(self, step=None):
        global _ocr_reader
        reader = init_ocr_reader(self.log)
        if reader is None: return False
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
            p = resource_path(f"images/btn_{i}.png")
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
            t_s = cv2.resize(t_img, (int(t_img.shape[1]*scale), int(t_img.shape[0]*scale)), interpolation=cv2.INTER_AREA)
            found = False
            for _ in range(3):
                scr = self.get_screenshot()
                if scr is not None:
                    res = cv2.matchTemplate(cv2.cvtColor(scr, cv2.COLOR_BGR2GRAY), t_s, cv2.TM_CCOEFF_NORMED)
                    _, mv, _, ml = cv2.minMaxLoc(res)
                    if mv >= 0.85:
                        self.call_adb(["shell", "input", "tap", str(ml[0]+t_s.shape[1]//2), str(ml[1]+t_s.shape[0]//2)])
                        found = True; time.sleep(0.3); break
                time.sleep(0.5)
        return True

    def wait_for_players_logic(self, step):
        target = step.get("count", 4) + 1
        start = time.time()
        while time.time() - start < step.get("timeout", 300) and self.running:
            with self.shared_data["lock"]: curr = self.shared_data.get("joined_counts", {}).get(self.group_id, 0)
            if curr >= target: return True
            self.update_status(f"Team {curr}/{target}"); time.sleep(2)
        return False

    def sync_autowin_logic(self, step):
        start = time.time()
        with self.shared_data["lock"]:
            self.shared_data["autowin_barrier"][self.group_id] = self.shared_data["autowin_barrier"].get(self.group_id, 0) + 1
        while time.time() - start < 120 and self.running:
            with self.shared_data["lock"]:
                if self.shared_data["autowin_barrier"].get(self.group_id, 0) >= 5: break
            time.sleep(0.5)
        self.click_image_logic({"action": "click_image_if", "target": "images/autowin.png", "timeout": 20, "confidence": 0.9})
        with self.shared_data["lock"]: self.shared_data["autowin_barrier"][self.group_id] = 0
        return True

    def run(self, accounts, modes, worker_index, shared_data):
        self.accounts_list = accounts
        self.modes = modes
        self.worker_index = worker_index
        self.group_id = self.worker_index // 5
        self.shared_data = shared_data
        self.running = True
        
        # --- FULL SCRIPTS FROM LD VERSION ---
        login_script = [
            {"action": "click_image_if", "target": "images/game_logo.png", "timeout": 10, "confidence": 0.7},
            {"action": "click_image", "target": "images/login_garena.png", "timeout": 420, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/login_garena.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target1": "images/username.png","target2": "images/account_input.png", "timeout": 60, "confidence": 0.7},
            {"action": "input_account"},
            {"action": "click_image", "target1": "images/password.png","target2": "images/input_password.png", "timeout": 60, "confidence": 0.7},
            {"action": "input_password"},
            {"action": "click_image", "target1": "images/login.png", "target2": "images/login_now.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 5},
            {"action": "click_image_if", "target1": "images/login.png", "target2": "images/login_now.png", "timeout": 5, "confidence": 0.7},
            {"action": "click_image", "target": "images/ok2.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 5},
            {"action": "click_image_if", "target": "images/ok2.png", "timeout": 4, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/batdau.png", "timeout": 6, "confidence": 0.7},
            {
                "action": "click_image_if", 
                "target": "images/vao_tran_button_1.png", 
                "timeout": 20, 
                "confidence": 0.7,
                "then": [
                    {"action": "click_image_if", "target": "images/vao_tran_button_1.png", "timeout": 3, "confidence": 0.7},
                    {"action": "wait", "timeout": 5},
                    {"action": "click_image", "target": "images/vao_tran_button_2.png", "timeout": 30, "confidence": 0.7},
                    {"action": "click_image_if", "target": "images/vao_tran_button_2.png", "timeout": 4, "confidence": 0.7}
                ]
            },
            {"action": "click_image_if", "target": "images/skip.png", "timeout": 45, "confidence": 0.7},
            {
                "action": "click_image_if", 
                "target": "images/vao_button.png", 
                "timeout": 10, 
                "confidence": 0.7,
                "then": [
                   {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.7},
                   {"action": "click_image_if", "target": "images/autowin.png", "timeout": 20, "confidence": 0.7},
                   {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.7},
                   {"action": "click_any", "wait": 30},
                   {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.7},
                   {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.7},
                ]
            },
            {"action": "wait", "timeout": 5},
            {"action": "click_any"},
            {"action": "press_esc", "wait": 3},
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
        ]
        
        tutorial_script = [
            {"action": "click_image", "target": "images/pvp.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/1v1.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/close.png", "timeout": 5, "confidence": 0.7},
            {"action": "click_image", "target": "images/pve.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/logo1.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/autowin.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/ready.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/tuong2.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/victory.png", "timeout": 120, "confidence": 0.7},
            {"action": "wait", "timeout": 20},
            {"action": "click_image", "target": "images/lobby.png", "timeout": 20, "confidence": 0.7},
            {"action": "press_esc", "wait": 5},
            {"action": "click_image", "target": "images/event_default.png", "timeout": 20, "confidence": 0.7},
            {"action": "press_esc", "wait": 3},
        ]

        dinh_game_script = [
            {"action": "click_image", "target": "images/dauthuong.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image", "target": "images/ready.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/sansang5v5.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 7},
            {"action": "click_image_if", "target": "images/ok3.png", "timeout": 15, "confidence": 0.7},
            {"action": "click_image", "target": "images/victory.png", "timeout": 600, "confidence": 0.7},
            {"action": "wait", "timeout": 10},
            {"action": "press_esc", "wait": 2},
        ]

        teamup_host_script = [
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images/team5.png", "timeout": 60, "confidence": 0.7},
            {"action": "get_room_id", "timeout": 30, "roi": [0.50, 0.0, 0.30, 0.10]},
            {"action": "wait_for_players", "count": 4, "timeout": 300},
            {"action": "click_image", "target": "images/pve.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/ready.png", "timeout": 30, "confidence": 0.7},
        ]
        
        teamup_guest_script = [
            {"action": "press_esc", "wait": 2},
            {"action": "click_image", "target": "images/pvp.png", "timeout": 60, "confidence": 0.7},
            {"action": "click_image", "target": "images/idphong.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait_for_room", "timeout": 300},
            {"action": "input_room_id"},
            {"action": "click_image", "target": "images/vao.png", "timeout": 30, "confidence": 0.7},
        ]

        tuong_target = f"images/tuong{(self.worker_index % 5) + 1}.png"
        shared_battle_script = [
            {"action": "click_image", "target": "images/logo1.png", "timeout": 50, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/autowin.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image", "target": "images/minimize.png", "timeout": 20, "confidence": 0.7},
            {"action": "click_image_if", "target": "images/sansang5v5.png", "timeout": 50, "confidence": 0.7},
            {"action": "click_image_if", "target": tuong_target, "timeout": 10, "confidence": 0.7},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.7},
            {"action": "wait", "timeout": 10},
            {"action": "click_image", "target": "images/victory.png", "timeout": 600, "confidence": 0.7},
            {"action": "click_image", "target": "images/tiep_tuc1.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/daulai.png", "timeout": 20, "confidence": 0.7},
        ]

        uplevel_script = [
            {"action": "click_image", "target": "images/logo.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/home.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/cai_dat_button.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/logout.png", "timeout": 30, "confidence": 0.7},
            {"action": "click_image", "target": "images/ok.png", "timeout": 30, "confidence": 0.7},
            {"action": "wait", "timeout": 15},
        ]
        
        # Assemble script based on modes
        self.script = []
        if self.modes.get("login"): 
            self.script += login_script

        if self.modes.get("tutorial"): self.script += tutorial_script
        if self.modes.get("dinh_game"): self.script += dinh_game_script
        if self.modes.get("teamup"):
            if self.worker_index % 5 == 0: self.script += teamup_host_script
            else: self.script += teamup_guest_script
            self.script.append({"action": "wait_for_players", "count": 4, "timeout": 300})
            battle_loop = {"action": "loop", "count": self.modes.get("battle_count", 2), "steps": shared_battle_script}
            self.script.append(battle_loop)
        
        self.script += uplevel_script # ALWAYS LOGOUT

        while self.running:
            self.current_account = None
            with FILE_LOCK:
                for acc in self.accounts_list:
                    if not acc.get("used"):
                        acc["used"] = True; self.current_account = acc
                        self.update_ui_func(); break
            if not self.current_account: break
            self.log(f">> START: {self.current_account['tk']}")
            
            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step):
                    success = False; break
            
            if self.running:
                self.report_stats_func(success, self.current_account)
                self.accounts_processed += 1
                if self.accounts_processed >= self.restart_threshold:
                    self.restart_device(); self.accounts_processed = 0
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
        self.device_cards = {}
        
        try:
            self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(64, 64))
            self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
            self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))
        except:
            self.logo_img = self.start_icon = self.stop_icon = None
        
        self.setup_layout()
        self.scan_devices()
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
        self.mode_dinh_game = ctk.CTkCheckBox(self.mode_frame, text="DÍNH GAME"); self.mode_dinh_game.grid(row=0, column=2); self.mode_dinh_game.select()
        self.mode_teamup = ctk.CTkCheckBox(self.mode_frame, text="GHÉP ĐỘI"); self.mode_teamup.grid(row=0, column=3); self.mode_teamup.select()
        
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
        self.load_adb_config()

    def find_adb(self):
        paths = ["adb", resource_path("adb.exe"), r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
        for p in paths:
            try:
                if p == "adb" or os.path.exists(p):
                    subprocess.run([p, "version"], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
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
            serials.sort()
        except Exception as e:
            print(f"Lỗi quét ADB: {e}")

        # Update UI in main thread
        self.after(0, lambda: self._update_device_list_ui(serials))

    def _update_device_list_ui(self, serials):
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        for i, s in enumerate(serials):
            self.device_map[s] = i
            card = ctk.CTkFrame(self.device_list_frame, height=55, fg_color="#252525", corner_radius=8)
            card.pack(fill="x", pady=4, padx=8)
            
            # Left side: Phone index and Serial
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", padx=15)
            ctk.CTkLabel(info_frame, text=f"PHONE {i+1}", font=("Arial", 11, "bold"), text_color=ACCENT_GREEN).pack(anchor="w")
            ctk.CTkLabel(info_frame, text=s, font=("Arial", 10), text_color="#888").pack(anchor="w")
            
            # Right side: Control buttons and Status
            ctrl_frame = ctk.CTkFrame(card, fg_color="transparent")
            ctrl_frame.pack(side="right", padx=10)
            
            status_lbl = ctk.CTkLabel(ctrl_frame, text="Ready", text_color="#888", font=("Arial", 11))
            status_lbl.pack(side="left", padx=10)
            
            btn_start_sq = ctk.CTkButton(ctrl_frame, text="", image=self.start_icon, width=32, height=32, fg_color="#2d3748", hover_color="#10b981", command=lambda sn=s: self.start_single_device(sn))
            btn_start_sq.pack(side="left", padx=2)
            
            btn_stop_sq = ctk.CTkButton(ctrl_frame, text="", image=self.stop_icon, width=32, height=32, fg_color="#2d3748", hover_color=ACCENT_RED, command=lambda sn=s: self.stop_single_device(sn))
            btn_stop_sq.pack(side="left", padx=2)
            
            self.device_cards[s] = {"status": status_lbl, "start_btn": btn_start_sq, "stop_btn": btn_stop_sq}
            
        self.btn_refresh.configure(state="normal", text="Làm Mới")
        if not serials:
            ctk.CTkLabel(self.device_list_frame, text="Không tìm thấy thiết bị nào.", text_color="#888").pack(pady=10)


    def load_accounts(self):
        p = fd.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not p: return
        self.account_file_path = p
        self.accounts_data = []
        with open(p, 'r', encoding='utf-8') as f:
            for l in f:
                parts = l.strip().split('|')
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
        modes = {"login":self.mode_login.get(), "tutorial":self.mode_tutorial.get(), "dinh_game":self.mode_dinh_game.get(), "teamup":self.mode_teamup.get(), "battle_count":b_count}
        
        def update_single_status():
             # Find status label for this serial
             if serial in self.device_cards:
                 for w in self.active_workers:
                     if w.device_id == serial:
                         self.device_cards[serial]["status"].configure(text=w.status, text_color="#4ADE80" if not w.is_lagging else "#FB7185")
                         break
             self.update_all_ui()

        worker = AutoClickerInstance(serial, self.adb_path, self.add_log, update_single_status, self.report_stats)
        self.active_workers.append(worker)
        threading.Thread(target=worker.run, args=(self.accounts_data, modes, self.device_map[serial], self.shared_data), daemon=True).start()
        self.add_log(f"Đã bắt chạy thiết bị: {serial}")

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
        print(full_text)
        try:
            self.log_txt.insert("end", full_text + "\n")
            self.log_txt.see("end")
        except: pass

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

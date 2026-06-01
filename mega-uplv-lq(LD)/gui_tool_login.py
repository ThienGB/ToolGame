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


import tkinter.filedialog as fd

SECRET_KEY = "RyoUTE_MegaUpLvLQ_2026"
LICENSE_FILE = "license.bin"

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
        self.ld_console_path = None # Sẽ được gán từ App

    def log(self, msg):
        self.log_func(f"[{self.device_id}] {msg}")

    def update_status(self, status, is_lagging=False):
        self.status = status
        self.is_lagging = is_lagging
        self.update_ui_func()

    def input_text_robust(self, text):
        """Nhập text qua ADB, hỗ trợ mọi ký tự đặc biệt."""
        if not text: return
        # Tách theo space vì space phải dùng %s trong adb input text
        parts = text.split(' ')
        for i, part in enumerate(parts):
            if part:
                # shlex.quote tạo chuỗi an toàn cho shell
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

        if action == "click_coords":
            res = self.click_coords_logic(step)
        elif action == "input_account":
            res = self.input_account_logic()
        elif action == "input_password":
            res = self.input_password_logic()
        elif action == "loop":
            count = step.get("count", 1)
            sub_steps = step.get("steps", [])
            for i in range(count):
                if not self.running: return False
                self.log(f"--- Bắt đầu lặp lượt {i+1}/{count} ---")
                for s in sub_steps:
                    if not self.execute_step(s): return False
            res = True
        elif action == "clear_android_data":
            pkg = step.get("package")
            self.call_adb(["shell", "pm", "clear", pkg])
            res = True
        # Kiểm tra lag
        duration = time.time() - self.last_step_time
        if duration > 35: 
             self.update_status("Lag", True)
        else:
             self.update_status("Đang chạy", False)

        return res


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

    def input_text_logic(self, step):
        content = step.get("content", "")
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        self.input_text_robust(content)
        return True

    def input_account_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("tk", "")
        # Xóa 30 lần trước khi nhập như yêu cầu
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 30)
        self.input_text_robust(content)
        return True

    def input_password_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("mk", "")
        # Xóa 30 lần trước khi nhập như yêu cầu
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 30)
        self.input_text_robust(content)
        return True

        return True

    def run(self, accounts, worker_index):
        self.accounts_list = accounts
        self.worker_index = worker_index
        self.running = True
        
        # 1. GIAI ĐOẠN LOGIN (Đã tối giản)
        login_script = [
            {"action": "click_coords", "x": 193, "y": 444, "timeout": 2}, # garena
            {"action": "click_coords", "x": 151, "y": 256, "timeout": 3}, # input_acc
            {"action": "input_account"},
            {"action": "click_coords", "x": 130, "y": 319, "timeout": 2}, # input_pass
            {"action": "input_password"},
            {"action": "click_coords", "x": 476, "y": 391, "timeout": 2}, # logic (login)
            {"action": "click_coords", "x": 476, "y": 391, "timeout": 4},
            {"action": "click_coords", "x": 476, "y": 391, "timeout": 4},
            
            {"action": "click_coords", "x": 770, "y": 502, "timeout": 4},
            {"action": "click_coords", "x": 770, "y": 502, "timeout": 4}, # ok
            {"action": "click_coords", "x": 476, "y": 458, "timeout": 3}, # bắt đầu
            
            {"action": "clear_android_data", "package": "com.garena.gaslite"},
        ]

        while self.running:
            # FLOW ĐƠN GIẢN: Chỉ chạy login_script 1 vòng rồi dừng
            self.script = login_script
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
            
            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step):
                    self.log("THẤT BẠI: Quá thời gian. Đang thử lại...")
                    success = False
                    break
            
            if self.running:
                if success:
                    self.update_ui_func()
                    self.report_stats_func(True, self.current_account)
                else:
                    self.report_stats_func(False, self.current_account)
                    
                self.log("HOÀN TẤT 1 VÒNG: Dừng lại.")
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
        self.title("MegaLogin")
        self.geometry("900x200")
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
        
        self.device_map = {} # serial -> absolute_index (0, 1, 2...)
        self.team_frames = {}

        # Assets (Sử dụng resource_path để đóng gói)
        self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(40, 40))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(18, 18))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(18, 18))

        self.setup_layout()
        self.load_config() # Tải đường dẫn đã lưu
        self.scan_devices()
        

    def find_adb(self):
        paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
        for p in paths:
            try:
                subprocess.run([p, "version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return p
            except: continue
        return "adb"

    def setup_layout(self):
        # Toàn bộ dùng 1 frame chính nằm ngang
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # 1. Block TRÁI: Logo + Nút Điều Khiển
        left_block = ctk.CTkFrame(self.main_frame, fg_color=CARD_COLOR, corner_radius=10, width=180)
        left_block.pack(side="left", fill="y", padx=5, pady=5)
        left_block.pack_propagate(False)

        ctk.CTkLabel(left_block, image=self.logo_img, text="").pack(pady=(10, 0))
        ctk.CTkLabel(left_block, text="MegaLogin v2.5", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_GREEN).pack()
        
        self.btn_start = ctk.CTkButton(left_block, text="START ALL", command=self.start_all, height=28, font=ctk.CTkFont(size=11, weight="bold"))
        self.btn_start.pack(padx=10, pady=(10, 5), fill="x")
        
        self.btn_stop = ctk.CTkButton(left_block, text="STOP ALL", command=self.stop_all, fg_color="#333", height=24, font=ctk.CTkFont(size=10))
        self.btn_stop.pack(padx=10, pady=0, fill="x")

        # 2. Block GIỮA: Cấu hình & Thống kê
        mid_block = ctk.CTkFrame(self.main_frame, fg_color=CARD_COLOR, corner_radius=10, width=220)
        mid_block.pack(side="left", fill="y", padx=5, pady=5)
        mid_block.pack_propagate(False)

        ctk.CTkLabel(mid_block, text="CẤU HÌNH", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888").pack(pady=(10, 2))
        self.ld_path_entry = ctk.CTkEntry(mid_block, placeholder_text="Path LD", height=22, font=ctk.CTkFont(size=9))
        self.ld_path_entry.pack(padx=10, pady=2, fill="x")
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        
        ctk.CTkButton(mid_block, text="NẠP FILE TÀI KHOẢN", command=self.load_accounts, fg_color="#EAB308", text_color="#000", height=24, font=ctk.CTkFont(size=10, weight="bold")).pack(padx=10, pady=5, fill="x")

        # Thống kê nằm dưới config
        self.stats_frame = ctk.CTkFrame(mid_block, fg_color="#222", corner_radius=6)
        self.stats_frame.pack(padx=10, pady=(5, 10), fill="both", expand=True)
        self.stats_label = ctk.CTkLabel(self.stats_frame, text="Thành công: 0 | Đang chạy: 0\nLag: 0 | Tổng Acc: 0", font=ctk.CTkFont(size=10, weight="bold"))
        self.stats_label.pack(expand=True)

        # 3. Block PHẢI: Danh sách thiết bị (Cuộn ngang/dọc)
        right_block = ctk.CTkFrame(self.main_frame, fg_color=CARD_COLOR, corner_radius=10)
        right_block.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        
        # Header cho danh sách thiết bị
        device_header = ctk.CTkFrame(right_block, fg_color="transparent")
        device_header.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(device_header, text="TRẠNG THÁI THIẾT BỊ", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888").pack(side="left")
        
        # Nút Làm mới quét ADB
        self.btn_refresh = ctk.CTkButton(device_header, text="LÀM MỚI", command=self.scan_devices, 
                                          width=70, height=20, font=ctk.CTkFont(size=9, weight="bold"),
                                          fg_color="#333", hover_color="#444")
        self.btn_refresh.pack(side="right")
        
        self.device_list_frame = ctk.CTkScrollableFrame(right_block, fg_color="transparent", corner_radius=0)
        self.device_list_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self.device_cards = {}



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
        active = sum(1 for w in self.active_workers if w.running)
        lags = sum(1 for w in self.active_workers if w.is_lagging)
        total_acc = len(self.accounts_data)
        self.stats_label.configure(text=f"Thành công: {self.success_count} | Đang chạy: {active}\nLag: {lags} | Tổng Acc: {total_acc}")


    def update_all_ui(self):
        def _update():
            self.update_stats_ui()
        self.after(0, _update)

    def save_config(self):
        config = {
            "ld_path": self.ld_path_entry.get().strip()
        }
        with open("config.json", "w") as f:
            json.dump(config, f)
        self.add_log("HỆ THỐNG: Đã lưu cấu hình LDPlayer.")

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                    path = config.get("ld_path", "")
                    if path:
                        self.ld_path_entry.delete(0, "end")
                        self.ld_path_entry.insert(0, path)
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
        # Chạy quét máy ảo trong luồng riêng để tránh lag UI
        threading.Thread(target=self._perform_scan, daemon=True).start()

    def _perform_scan(self):
        base_path = self.ld_path_entry.get().strip()
        self.adb_path = os.path.join(base_path, "adb.exe")
        if not os.path.exists(self.adb_path): self.adb_path = "adb"
        
        try:
            # 1. Tìm file console điều khiển
            ldconsole_path = None
            for exe in ["ldconsole.exe", "dnconsole.exe", "ld.exe"]:
                p = os.path.join(base_path, exe)
                if os.path.exists(p):
                    ldconsole_path = p
                    break
            
            # 2. Lấy danh sách máy ảo đang chạy và connect ADB
            if ldconsole_path:
                try:
                    res_ld = subprocess.run([ldconsole_path, "list2"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                    for line in res_ld.stdout.splitlines():
                        parts = line.split(',')
                        if len(parts) >= 5 and parts[4] == '1': # Chỉ lấy máy ảo đang ON (Status = 1)
                            idx = parts[0]
                            port = 5554 + (int(idx) * 2)
                            try:
                                subprocess.run([self.adb_path, "connect", f"127.0.0.1:{port}"], 
                                             capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                            except: pass
                except: pass

            # 3. Quét dự phòng các port phổ biến
            for i in range(10): 
                port = 5554 + (i * 2)
                subprocess.Popen([self.adb_path, "connect", f"127.0.0.1:{port}"], 
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                               creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Đợi ADB cập nhật danh sách
            time.sleep(3)

            # 4. Lấy danh sách thiết bị cuối cùng
            try:
                res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                lines = res.stdout.strip().split('\n')[1:]
                device_serials = [line.split('\t')[0] for line in lines if "device" in line]
            except:
                device_serials = []
            
            # Cập nhật UI trên main thread
            self.after(0, lambda: self._update_device_ui(device_serials))
        except Exception as e:
            self.add_log(f"LỖI QUÉT: {e}")

    def _update_device_ui(self, device_serials):
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        self.team_frames = {}
        self.device_map = {}
        
        try:
            # Lấy tất cả serials và gán index dựa trên port ADB để sắp xếp
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
                self.update_stats_ui()
                return

            # Hiển thị danh sách dọc đơn giản
            for serial in sorted(self.device_map.keys(), key=lambda s: self.device_map[s]):
                abs_idx = self.get_absolute_index(serial)
                
                card = ctk.CTkFrame(self.device_list_frame, fg_color="#222", corner_radius=4, height=24)
                card.pack(fill="x", padx=2, pady=1)
                card.pack_propagate(False)
                
                # Index & Serial
                name_label = ctk.CTkLabel(card, text=f"[{abs_idx}] {serial}", font=ctk.CTkFont(size=9, weight="bold"))
                name_label.pack(side="left", padx=5)
                
                # Status
                status_label = ctk.CTkLabel(card, text="Wait", font=ctk.CTkFont(size=9), text_color="#888")
                status_label.pack(side="right", padx=5)
                
                self.device_cards[serial] = {
                    "card": card,
                    "status": status_label,
                    "name": name_label
                }
            self.update_stats_ui()
        except Exception as e:
            self.add_log(f"LỖI CẬP NHẬT UI THIẾT BỊ: {e}")

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
        if not self.device_cards:
            self.add_log("LỖI: Không tìm thấy thiết bị nào. Hãy quét thiết bị trước.")
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

        # Start all devices
        self.active_workers = [] 
        for serial in self.device_cards:
            worker_index = self.device_map.get(serial, 0)
            worker = AutoClickerInstance(serial, self.adb_path, self.add_log, self.update_all_ui, self.report_stats)
            
            base_ld_path = self.ld_path_entry.get().strip()
            worker.ld_console_path = base_ld_path if base_ld_path.endswith(".exe") else os.path.join(base_ld_path, "ldconsole.exe")
                
            self.active_workers.append(worker)
            t = threading.Thread(target=worker.run, args=(self.accounts_data, worker_index), daemon=True)
            t.start()

    def stop_all(self):
        self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")
        self.btn_stop.configure(state="disabled", fg_color="#333")
        
        # Dừng tất cả worker đang chạy
        for worker in self.active_workers:
            worker.running = False
            
        self.add_log("!!! ĐANG DỪNG TẤT CẢ CÁC MÁY...")


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

# pyinstaller --noconfirm --onefile --windowed --icon "logo.png" --name "AutoLoginLQ_Pro" --add-data "logo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool_login.py
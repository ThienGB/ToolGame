import json
import time
import os
import subprocess
import threading
import cv2
import numpy as np
import customtkinter as ctk
from PIL import Image
from datetime import datetime
import sys
import hashlib
import base64
import uuid
try:
    import winreg
except ImportError:
    winreg = None

from tkinter import filedialog

# --- Paths & Constants ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

IMAGE_CACHE = {}
def get_cached_image(path):
    real_path = resource_path(path)
    if not os.path.exists(real_path): return None
    if path not in IMAGE_CACHE:
        IMAGE_CACHE[path] = cv2.imread(real_path, cv2.IMREAD_COLOR)
    return IMAGE_CACHE[path]

SECRET_KEY = "RyoUTE_MegaUpLvCF_2026"
LICENSE_FILE = "license.bin"
NAV_COLOR = "#0F0F0F"
BG_COLOR = "#121212"
CARD_COLOR = "#1D1D1D"
ACCENT_GREEN = "#00D2FF"
ACCENT_PURPLE = "#A855F7"
ACCENT_RED = "#EF4444"

# --- Security logic ---
def get_hwid():
    try:
        def get_cmd(cmd):
            try:
                out = subprocess.check_output(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW).decode().strip()
                return out.split('\n')[1].strip() if len(out.split('\n')) > 1 else ""
            except: return ""
        combined = f"U:{get_cmd('wmic csproduct get uuid')}|D:{get_cmd('wmic diskdrive where index=0 get serialnumber')}|M:{uuid.getnode()}"
        return hashlib.sha256(combined.encode()).hexdigest()[:24].upper()
    except: return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:24].upper()

def verify_license(key, hwid):
    try:
        decoded = base64.b64decode(key).decode()
        exp, sig = decoded.split('|')
        if sig != hashlib.sha256(f"{exp}{hwid}{SECRET_KEY}".encode()).hexdigest()[:10]: return False, "Invalid"
        if datetime.now() > datetime.strptime(exp, "%Y-%m-%d %H:%M:%S"): return False, "Expired"
        return True, exp
    except: return False, "Error"

# --- Automation Logic ---
class AutoClickerInstance:
    def __init__(self, device_id, adb_path, log_func, update_ui_func, report_stats_func):
        self.device_id, self.adb_path = device_id, adb_path
        self.log_func, self.update_ui_func, self.report_stats_func = log_func, update_ui_func, report_stats_func
        self.running, self.status, self.is_lagging = False, "Đang chờ", False
        self.current_account = None
        self.account_lock = None # Sẽ được gán từ MultiPremiumApp

    def log(self, msg): self.log_func(f"[{self.device_id}] {msg}")
    
    def call_adb(self, args, timeout=15):
        try:
            return subprocess.run([self.adb_path, "-s", self.device_id] + args, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess([], 1, b"", b"timeout")
        except Exception as e:
            return subprocess.CompletedProcess([], 1, b"", str(e).encode())

    def get_screenshot(self):
        try:
            # Ưu tiên dùng exec-out để nhận byte chuẩn
            cmd = [self.adb_path, "-s", self.device_id, "exec-out", "screencap", "-p"]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                stdout, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); return None
            
            if process.returncode != 0 or not stdout:
                # Chế độ dự phòng
                cmd = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    stdout, _ = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); return None
                if process.returncode != 0 or not stdout: return None
                stdout = stdout.replace(b"\r\n", b"\n")
            
            return cv2.imdecode(np.frombuffer(stdout, np.uint8), cv2.IMREAD_COLOR)
        except: return None

    def escape_adb_text(self, text):
        chars = ['\\', '"', "'", '&', '>', '<', '|', ';', '(', ')', '*', '?', '$', '!', '#', '%', '{', '}', '~', '[', ']', '^', '@']
        return "".join([f"\\{c}" if c in chars else ("%s" if c == ' ' else c) for c in text])

    def execute_step(self, step):
        if not self.running: return False
        action, start = step.get("action"), time.time()
        res = True
        if action in ["click_image", "click_image_if"]: res = self.click_image_logic(step) or action == "click_image_if"
        elif action == "wait": time.sleep(step.get("timeout", 1))
        elif action == "input_account_logic":
            self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
            self.call_adb(["shell", "input", "text", self.escape_adb_text(self.current_account["tk"])])
        elif action == "input_password_logic":
            self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
            self.call_adb(["shell", "input", "text", self.escape_adb_text(self.current_account["mk"])])
        elif action == "clear_android_data":
            pkg = step.get("package")
            self.call_adb(["shell", "pm", "clear", pkg])
            res = True
        elif action == "swipe":
            res = self.swipe_logic(step)
        elif action == "click_coords":
            res = self.click_coords_logic(step)
        
        self.status, self.is_lagging = "Đang chạy", (time.time() - start) > 35
        self.update_ui_func()
        return res

    def click_image_logic(self, step):
        targets = [step.get("target")] if step.get("target") else [step.get(f"target{i}") for i in range(1, 11) if step.get(f"target{i}")]
        timeout, conf = step.get("timeout", 10), step.get("confidence", 0.8)
        imgs = [(t, get_cached_image(t)) for t in targets if get_cached_image(t) is not None]
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                for path, t_img in imgs:
                    res = cv2.matchTemplate(screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, val, _, loc = cv2.minMaxLoc(res)
                    if val >= conf:
                        h, w = t_img.shape[:2]
                        self.call_adb(["shell", "input", "tap", str(loc[0]+w//2), str(loc[1]+h//2)])
                        self.log(f"CLICK: {os.path.basename(path)} ({val:.2f})"); return True
            time.sleep(1)
        return False

    def swipe_logic(self, step):
        screen = self.get_screenshot()
        h, w = (screen.shape[:2]) if screen is not None else (1080, 1920)

        def get_val(val, max_v):
            if val is None: return 0
            return int(val * max_v) if isinstance(val, (float, int)) and val <= 1.0 else int(val)

        x1, y1 = get_val(step.get("x1", 0.5), w), get_val(step.get("y1", 0.8), h)
        x2, y2 = get_val(step.get("x2", 0.5), w), get_val(step.get("y2", 0.3), h)
        duration = step.get("duration", 500)

        self.call_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
        self.log(f"SWIPE: ({x1}, {y1}) -> ({x2}, {y2}) trong {duration}ms")
        return True

    def click_coords_logic(self, step):
        x, y = step.get("x"), step.get("y")
        if x is not None and y is not None:
            delay = step.get("timeout", 0)
            if delay > 0: time.sleep(delay)
            self.call_adb(["shell", "input", "tap", str(x), str(y)])
            self.log(f"CLICK TỌA ĐỘ: ({x}, {y})")
            return True
        return False

    def run(self, accounts):
        self.running = True
        self.script = [
            # {"action": "clear_android_data", "package": "com.tencent.stc.cfl"},
            {"action": "swipe", "x1": 0.5, "y1": 0.5, "x2": 0.4, "y2": 0.6, "duration": 800},
            {"action": "click_coords", "x": 325, "y": 550}, 
            
            
            
            
            {"action": "click_image_if", "target": "images/game_logo.png", "timeout": 5},
            {"action": "click_image", "target": "images/more.png", "timeout": 180},
            {"action": "click_image", "target": "images/lipass.png", "timeout": 60},
            {"action": "click_image", "target": "images/passwordlogin.png", "timeout": 30},
            {"action": "click_image", "target": "images/emailadress.png", "timeout": 60},
            {"action": "input_account_logic"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 10},
            {"action": "click_image", "target": "images/password.png", "timeout": 30},
            {"action": "input_password_logic"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 10},
            {"action": "click_image", "target": "images/login.png", "timeout": 60},
            {"action": "click_image_if", "target1": "images/x.png", "target2": "images/x1.png", "timeout": 420},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target1": "images/x.png", "target2": "images/x1.png", "timeout": 20},
            {"action": "click_image_if", "target": "images/setting.jpg","timeout": 20},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/logout.png","timeout": 20},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images/logout.png","timeout": 5},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target": "images/confirm_name_btn.png","timeout": 20},
            {"action": "wait", "timeout": 20},
        ]
        while self.running:
            target = None
            with self.account_lock:
                target = next((a for a in accounts if not a.get('done') and not a.get('processing')), None)
                if target: target['processing'] = True
            
            if not target: break
            self.current_account = target
            self.log(f">> CHẠY: {target['tk']}")
            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step): success = False; break
            
            if success and self.running:
                target['done'] = True
                self.report_stats_func(True)
                self.update_ui_func()
            elif not success:
                with self.account_lock:
                    target['processing'] = False
                    target['fail_count'] = target.get('fail_count', 0) + 1
                    if target['fail_count'] >= 3:
                        target['done'] = True
                        self.log(f"!! BỎ QUA: {target['tk']} do lỗi quá 3 lần.")
                self.report_stats_func(False, target)
            self.log(">> Đã xong lượt, chuẩn bị tài khoản tiếp theo...")
            time.sleep(5)
        self.status = "Xong"; self.update_ui_func(); self.running = False

# --- UI Logic (MultiPremiumApp, LoginApp etc. continue from here) ---
class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvCFTool(LD)")
        self.geometry("1100x850")
        self.configure(fg_color=BG_COLOR)
        
        self.accounts_data, self.active_workers = [], []
        self.account_lock = threading.Lock()
        self.adb_path = self.find_adb()
        self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(80, 80))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(25, 25))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(25, 25))

        self.success_count = 0
        self.failure_count = 0

        self.setup_layout()
        self.load_config()
        self.scan_devices()

    def find_adb(self):
        for p in ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]:
            try:
                subprocess.run([p, "version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return p
            except: continue
        return "adb"

    def setup_layout(self):
        # 1. Sidebar
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=NAV_COLOR)
        self.sidebar.pack(side="left", fill="y")
        ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=(40,0))
        ctk.CTkLabel(self.sidebar, text="BẢNG ĐIỀU KHIỂN", font=ctk.CTkFont(size=22, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(20, 0))
        ctk.CTkLabel(self.sidebar, text="MegaUpLvCFTool(LD) v2.5", font=ctk.CTkFont(size=12)).pack(pady=(0, 20))

        # LDPlayer Path Config
        self.path_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10)
        self.path_card.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.path_card, text="ĐƯỜNG DẪN LDPLAYER", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(5, 0))
        self.ld_path_entry = ctk.CTkEntry(self.path_card, placeholder_text="Ví dụ: C:\LDPlayer\LDPlayer9", height=30)
        self.ld_path_entry.pack(padx=10, pady=10, fill="x")
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        ctk.CTkButton(self.path_card, text="Lưu Cấu Hình", command=self.save_config, height=25).pack(padx=10, pady=(0, 10), fill="x")

        # Account Input Area
        self.acc_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333")
        self.acc_card.pack(padx=20, pady=10, fill="x")
        ctk.CTkButton(self.acc_card, text="NẠP FILE TK|MK (.txt)", command=self.load_file, fg_color=ACCENT_PURPLE, height=40, font=ctk.CTkFont(weight="bold")).pack(padx=15, pady=15, fill="x")

        # Controls
        self.btn_start = ctk.CTkButton(self.sidebar, text=" CHẠY TẤT CẢ", image=self.start_icon, compound="left", command=self.start_all, height=50, corner_radius=10, font=ctk.CTkFont(size=16, weight="bold"))
        self.btn_start.pack(padx=20, pady=(30, 10), fill="x")
        self.btn_stop = ctk.CTkButton(self.sidebar, text=" DỪNG TẤT CẢ", image=self.stop_icon, compound="left", command=self.stop_all, fg_color="#333", height=50, corner_radius=10)
        self.btn_stop.pack(padx=20, pady=10, fill="x")
        
        ctk.CTkLabel(self.sidebar, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=11), text_color="#666").pack(side="bottom", pady=20)

        # 2. Main Area
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(side="right", fill="both", expand=True, padx=25, pady=25)

        # Device Selection Card
        inst_f = ctk.CTkFrame(main, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333")
        inst_f.pack(fill="x", pady=(0, 20))
        
        header_f = ctk.CTkFrame(inst_f, fg_color="transparent")
        header_f.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(header_f, text="THIẾT BỊ ĐANG MỞ", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN).pack(side="left")
        
        self.btn_refresh = ctk.CTkButton(header_f, text="Làm Mới Danh Sách", command=self.scan_devices, height=26, width=120, font=ctk.CTkFont(size=11, weight="bold"))
        self.btn_refresh.pack(side="right")
        self.dev_frame = ctk.CTkScrollableFrame(inst_f, height=280, fg_color="transparent")
        self.dev_frame.pack(fill="x", padx=10, pady=(0, 15))
        for col in range(12): self.dev_frame.grid_columnconfigure(col, weight=1)
        self.device_cards = {}

        # Stats Card
        self.stats_card = ctk.CTkFrame(main, fg_color=CARD_COLOR, corner_radius=15)
        self.stats_card.pack(fill="both", expand=True)
        ctk.CTkLabel(self.stats_card, text="THÔNG SỐ HOẠT ĐỘNG", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_GREEN).pack(pady=15)
        self.stats_inner = ctk.CTkFrame(self.stats_card, fg_color="transparent")
        self.stats_inner.pack(fill="both", expand=True, padx=20)
        self.stats_inner.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.success_val = self.create_stat_item(self.stats_inner, "THÀNH CÔNG", "0", 0, 0, "#4ADE80")
        self.fail_val_ui = self.create_stat_item(self.stats_inner, "LỖI LƯỢT", "0", 0, 1, ACCENT_RED)
        self.lag_val = self.create_stat_item(self.stats_inner, "ĐANG LAG", "0", 0, 2, "#FB923C")
        self.rem_val = self.create_stat_item(self.stats_inner, "CÒN LẠI", "0", 0, 3, ACCENT_PURPLE)

    def create_stat_item(self, parent, title, value, row, col, color):
        f = ctk.CTkFrame(parent, fg_color="#252525", corner_radius=12)
        f.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888").pack(pady=(15, 0))
        lbl = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
        lbl.pack(pady=(5, 15))
        return lbl

    def save_config(self):
        with open("config.json", "w") as f: 
            json.dump({
                "ld_path": self.ld_path_entry.get().strip()
            }, f)

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
                    p = config.get("ld_path", "")
                    if p: 
                        self.ld_path_entry.delete(0, "end")
                        self.ld_path_entry.insert(0, p)
            except: pass

    def scan_devices(self):
        # Chạy quét máy ảo trong luồng riêng để tránh lag UI
        self.btn_refresh.configure(state="disabled", text="Đang quét...")
        threading.Thread(target=self._perform_scan, daemon=True).start()

    def _perform_scan(self):
        base_path = self.ld_path_entry.get().strip()
        self.adb_path = os.path.join(base_path, "adb.exe")
        if not os.path.exists(self.adb_path): self.adb_path = "adb"
        
        device_serials = []
        try:
            # Chỉ chạy lệnh adb devices để lấy danh sách thiết bị thực tế đang có
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            device_serials = [l.split('\t')[0] for l in res.stdout.strip().split('\n') if "device" in l and "\tdevice" in l]
        except: pass

        # Cập nhật UI trên main thread
        self.after(0, lambda: self._update_device_ui(device_serials))

    def _update_device_ui(self, device_serials):
        for w in self.dev_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        for i, d in enumerate(device_serials):
            card = ctk.CTkFrame(self.dev_frame, fg_color="#252525", corner_radius=6, border_width=1, border_color="#383838")
            card.grid(row=i // 12, column=i % 12, padx=3, pady=3, sticky="nsew")
            
            # Hiển thị chỉ port
            display_name = d.replace("emulator-", "").split(":")[-1]
            ctk.CTkLabel(card, text=display_name, font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(5,0))
            
            lbl = ctk.CTkLabel(card, text="Sẵn sàng", font=ctk.CTkFont(size=9), text_color="#666")
            lbl.pack(pady=(0,5)); self.device_cards[d] = {"status": lbl}
        
        self.btn_refresh.configure(state="normal", text="Làm Mới Danh Sách")
        self.refresh_ui()

    def load_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if p:
            with open(p, "r", encoding="utf-8") as f:
                for l in f:
                    if "|" in l: 
                        tk, mk = l.strip().split("|", 1)
                        self.accounts_data.append({"tk": tk, "mk": mk, "done": False})
            self.refresh_ui()

    def refresh_ui(self):
        self.after(0, self._refresh_ui_worker)

    def _refresh_ui_worker(self):
        try:
            # Update device card statuses
            for w in self.active_workers:
                if w.device_id in self.device_cards:
                    color = ACCENT_GREEN if w.running else "#888"
                    if w.is_lagging: color = "#FB923C"
                    self.device_cards[w.device_id]["status"].configure(text=w.status, text_color=color)

            done = sum(1 for a in self.accounts_data if a['done'])
            rem = sum(1 for a in self.accounts_data if not a['done'])
            self.success_val.configure(text=str(done))
            self.rem_val.configure(text=str(rem))
            self.fail_val_ui.configure(text=str(self.failure_count))
            self.lag_val.configure(text=str(sum(1 for w in self.active_workers if w.is_lagging)))
        except: pass

    def report_stats(self, success, account=None):
        if not success: 
            self.failure_count += 1
            if account:
                try:
                    with self.account_lock:
                        with open("that_bai.txt", "a", encoding="utf-8") as f:
                            f.write(f"{account['tk']}|{account['mk']}\n")
                except: pass
        self.after(0, self.refresh_ui)

    def start_all(self):
        if not self.accounts_data: return
        self.btn_start.configure(state="disabled", text=" ĐANG CHẠY...")
        for a in self.accounts_data: a['processing'] = False
        self.active_workers = []
        for d in self.device_cards.keys():
            w = AutoClickerInstance(d, self.adb_path, print, self.refresh_ui, self.report_stats)
            w.account_lock = self.account_lock
            self.active_workers.append(w)
            threading.Thread(target=w.run, args=(self.accounts_data,), daemon=True).start()

    def stop_all(self):
        for w in self.active_workers: w.running = False
        self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")

# --- Authentication Screen ---
class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KÍCH HOẠT MegaUpLvCFTool")
        self.geometry("500x550")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        self.hwid = get_hwid()
        self.setup_ui()

    def setup_ui(self):
        ctk.CTkLabel(self, text="MegaUpLvCFTool(LD)", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(40, 10))
        ctk.CTkLabel(self, text="HỆ THỐNG QUẢN LÝ BẢN QUYỀN", font=ctk.CTkFont(size=12)).pack(pady=(0, 30))
        hw_f = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=10)
        hw_f.pack(padx=40, fill="x")
        ctk.CTkLabel(hw_f, text="MÃ MÁY CỦA BẠN (HWID):", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(10, 0))
        self.hw_e = ctk.CTkEntry(hw_f, height=35, font=ctk.CTkFont(size=12)); self.hw_e.insert(0, self.hwid)
        self.hw_e.configure(state="readonly"); self.hw_e.pack(padx=20, pady=(5, 10), fill="x")
        ctk.CTkLabel(self, text="Hãy gửi mã trên cho Admin để nhận Key kích hoạt.", font=ctk.CTkFont(size=10), text_color="#888").pack(pady=5)
        self.key_i = ctk.CTkEntry(self, placeholder_text="Nhập Key kích hoạt tại đây...", height=40)
        self.key_i.pack(padx=40, pady=20, fill="x")
        ctk.CTkButton(self, text="KÍCH HOẠT NGAY", command=self.activate, height=45, corner_radius=10, font=ctk.CTkFont(weight="bold")).pack(padx=40, pady=5, fill="x")
        self.st_l = ctk.CTkLabel(self, text="", text_color=ACCENT_RED); self.st_l.pack(pady=10)
        ctk.CTkLabel(self, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=12, weight="bold"), text_color="#777").pack(pady=(30, 20))

    def activate(self):
        key = self.key_i.get().strip()
        if not key: self.st_l.configure(text="Vui lòng nhập Key!"); return
        v, exp = verify_license(key, self.hwid)
        if v:
            with open(LICENSE_FILE, "w") as f: f.write(key)
            self.launch()
        else: self.st_l.configure(text="Key không hợp lệ!")

    def launch(self): self.destroy(); MultiPremiumApp().mainloop()

if __name__ == "__main__":
    if os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r") as f:
            v, _ = verify_license(f.read().strip(), get_hwid())
            if v: MultiPremiumApp().mainloop(); sys.exit()
    LoginApp().mainloop()

# pyinstaller --noconfirm --onefile --windowed --name "MegaLoginCF" --add-data "images;images" --add-data "logo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool.py

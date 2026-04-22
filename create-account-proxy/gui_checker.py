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

NAV_COLOR = "#0F0F0F"
BG_COLOR = "#121212"
CARD_COLOR = "#1D1D1D"
ACCENT_GREEN = "#00D2FF"
ACCENT_PURPLE = "#A855F7"
ACCENT_RED = "#EF4444"


# --- Automation Logic ---
class AutoClickerInstance:
    def __init__(self, device_id, adb_path, log_func, update_ui_func, report_stats_func, claim_xu=False):
        self.device_id, self.adb_path = device_id, adb_path
        self.log_func, self.update_ui_func, self.report_stats_func = log_func, update_ui_func, report_stats_func
        self.running, self.status, self.is_lagging = False, "Đang chờ", False
        self.current_account = None
        self.account_lock = None 
        self.first_run = True

    def log(self, msg): 
        print(f"[{datetime.now().strftime('%H:%M:%S')}][{self.device_id}] {msg}")
    
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
        action = step.get("action")
        name = step.get("name", action)
        start = time.time()
        
        self.log(f"→ Thực hiện: {name}")
        res = True
        
        if action == "click_image": 
            res = self.click_image_logic(step)
        elif action == "wait": 
            self.log(f"  Đợi {step.get('timeout', 1)} giây...")
            time.sleep(step.get("timeout", 1))
        elif action == "input_text":
            self.log(f"  Nhập văn bản: {step.get('text', '')}")
            self.call_adb(["shell", "input", "text", self.escape_adb_text(step.get("text", ""))])
        elif action == "input_account_logic":
            self.log(f"  Đang nhập TK: {self.current_account['tk']}")
            self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
            self.call_adb(["shell", "input", "text", self.escape_adb_text(self.current_account["tk"])])
        elif action == "input_password_logic":
            self.log(f"  Đang nhập MK: *****")
            self.call_adb(["shell", "input", "keyevent"] + ["67"] * 40)
            self.call_adb(["shell", "input", "text", self.escape_adb_text(self.current_account["mk"])])
        elif action == "read_result":
            res = self.read_result_logic()
        
        if not res and action == "click_image":
            self.log(f"  [!] KHÔNG TÌM THẤY ẢNH: {step.get('target')}")

        self.status, self.is_lagging = name, (time.time() - start) > 35
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
                        cx, cy = loc[0] + w // 2, loc[1] + h // 2
                        self.call_adb(["shell", "input", "tap", str(cx), str(cy)])
                        self.log(f"  Done: Click [{os.path.basename(path)}] tại ({cx}, {cy}) - Conf: {val:.2f}")
                        return True
            time.sleep(1)
        return False

    def check_image(self, target, timeout=5, conf=0.8):
        t_img = get_cached_image(target)
        if t_img is None: return False
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                res = cv2.matchTemplate(screen, t_img, cv2.TM_CCOEFF_NORMED)
                _, val, _, _ = cv2.minMaxLoc(res)
                if val >= conf: return True
            time.sleep(1)
        return False

    def read_result_logic(self):
        self.log("Đang kiểm tra kết quả đăng nhập...")
        is_banned = self.check_image("images/banned.png", timeout=20)
        if is_banned:
            self.log("KẾT QUẢ: ACCOUNT BỊ BAN")
            self.report_stats_func("banned", self.current_account)
            return True
        else:
            self.log("KẾT QUẢ: THÀNH CÔNG")
            self.report_stats_func("success", self.current_account)
            return True

    def run(self, accounts):
        self.running = True
        self.script = [
            {"action": "click_image", "target": "images/search_input.png", "timeout": 180, "name": "Mở ô tìm kiếm"},
            {"action": "input_text", "text": "https://kientuong.lienquan.garena.vn/trang-chu", "name": "Nhập địa chỉ Web"},
            {"action": "click_image", "target": "images/search.png", "timeout": 30, "name": "Nhấn nút Tìm kiếm"},
            
            {"action": "click_image", "target": "images/garena.png", "timeout": 60, "name": "Chọn Login Garena"},
            {"action": "click_image", "target1": "images/account_input.png","target2": "images/account.png", "timeout": 60, "name": "Nhấn vào ô Tài khoản"},
            {"action": "input_account_logic", "name": "Điền User Garena"},
            {"action": "click_image", "target": "images/password_input.png", "timeout": 30, "name": "Nhấn vào ô Mật khẩu"},
            {"action": "input_password_logic", "name": "Điền Pass Garena"},
            {"action": "click_image", "target": "images/login.png", "timeout": 60, "name": "Nhấn Đăng nhập"},
            {"action": "read_result", "name": "Kiểm tra kết quả"},
            {"action": "click_image", "target": "images/logout.png", "timeout": 60, "name": "Đăng xuất acc"},
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
            
            # Thực hiện script
            start_index = 0 if self.first_run else 3
            current_script = self.script[start_index:]
            
            for step in current_script:
                if not self.running: break
                if not self.execute_step(step): 
                    success = False
                    break
            
            if success and self.running:
                target['done'] = True
                self.first_run = False 
                self.report_stats_func("done_cycle", target) # Gọi để cập nhật file
                self.update_ui_func()
            elif not success:
                with self.account_lock:
                    target['processing'] = False
                    target['fail_count'] = target.get('fail_count', 0) + 1
                    if target['fail_count'] >= 3:
                        target['done'] = True
                        self.log(f"!! BỎ QUA: {target['tk']} do lỗi quá 3 lần.")
                self.report_stats_func("fail", target)
            
            self.log(">> Đã xong lượt, chuẩn bị tài khoản tiếp theo...")
            time.sleep(5)
        self.status = "Xong"; self.update_ui_func(); self.running = False

# --- UI Logic (MultiPremiumApp, LoginApp etc. continue from here) ---
class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvCFTool(LD)")
        self.geometry("450x420")
        self.configure(fg_color=BG_COLOR)
        
        self.accounts_data, self.active_workers = [], []
        self.account_lock = threading.Lock()
        self.adb_path = self.find_adb()
        self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(60, 60))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))

        self.success_count = 0
        self.ban_count = 0
        self.device_serials = []
        self.input_file_path = None

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
        # Sidebar/Top Controls
        self.sidebar = ctk.CTkFrame(self, fg_color=NAV_COLOR, corner_radius=0)
        self.sidebar.pack(side="top", fill="x")
        
        # Header
        head_f = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        head_f.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(head_f, image=self.logo_img, text="").pack(side="left")
        ctk.CTkLabel(head_f, text="MegaUP v2.5", font=ctk.CTkFont(size=18, weight="bold"), text_color=ACCENT_GREEN).pack(side="left", padx=10)
        
        # Path config (compact)
        self.path_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=8)
        self.path_card.pack(padx=10, pady=5, side="left")
        self.ld_path_entry = ctk.CTkEntry(self.path_card, width=150, height=28, font=ctk.CTkFont(size=10))
        self.ld_path_entry.pack(side="left", padx=5, pady=5)
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        ctk.CTkButton(self.path_card, text="Lưu", width=40, height=25, command=self.save_config).pack(side="left", padx=5)

        # Buttons
        ctk.CTkButton(self.sidebar, text="Nạp File", command=self.load_file, fg_color=ACCENT_PURPLE, width=80, height=30).pack(side="left", padx=5)
        ctk.CTkButton(self.sidebar, text="Quét", command=self.scan_devices, width=60, height=30).pack(side="left", padx=5)
        
        # Main Area
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Control Row
        ctrl_f = ctk.CTkFrame(main, fg_color="transparent")
        ctrl_f.pack(fill="x", pady=5)
        self.btn_start = ctk.CTkButton(ctrl_f, text="BẮT ĐẦU", image=self.start_icon, compound="left", command=self.start_all, height=40, fg_color="#1E3A8A")
        self.btn_start.pack(side="left", fill="x", expand=True, padx=5)
        self.btn_stop = ctk.CTkButton(ctrl_f, text="DỪNG", image=self.stop_icon, compound="left", command=self.stop_all, height=40, fg_color="#333")
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=5)

        # Stats Area (Compact)
        self.stats_inner = ctk.CTkFrame(main, fg_color=CARD_COLOR, corner_radius=10)
        self.stats_inner.pack(fill="x", pady=5)
        self.stats_inner.columnconfigure((0, 1), weight=1)
        
        self.running_devices_val = self.create_stat_item(self.stats_inner, "MÁY CHẠY", "0", 0, 0, "#00D2FF")
        self.total_acc_val = self.create_stat_item(self.stats_inner, "TỔNG ACC", "0", 0, 1, ACCENT_PURPLE)
        self.success_val = self.create_stat_item(self.stats_inner, "THÀNH CÔNG", "0", 1, 0, "#4ADE80")
        self.ban_val = self.create_stat_item(self.stats_inner, "BỊ BAN", "0", 1, 1, ACCENT_RED)
        
        # Status Label
        self.status_label = ctk.CTkLabel(main, text="Sẵn sàng", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN)
        self.status_label.pack(pady=10)

    def create_stat_item(self, parent, title, value, row, col, color):
        f = ctk.CTkFrame(parent, fg_color="#252525", corner_radius=8)
        f.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=9, weight="bold"), text_color="#888").pack(pady=(5, 0))
        lbl = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color=color)
        lbl.pack(pady=(0, 5))
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
        self.status_label.configure(text="Đang quét thiết bị...")
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
        self.device_serials = device_serials
        self.status_label.configure(text=f"Tìm thấy {len(device_serials)} thiết bị")
        self.refresh_ui()

    def load_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if p:
            self.input_file_path = p
            self.accounts_data = [] # Reset data mới khi nạp file
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
            running_count = sum(1 for w in self.active_workers if w.running)
            self.running_devices_val.configure(text=str(running_count))
            self.total_acc_val.configure(text=str(len(self.accounts_data)))
            self.success_val.configure(text=str(self.success_count))
            self.ban_val.configure(text=str(self.ban_count))
        except: pass

    def report_stats(self, status, account=None):
        if status == "success":
            self.success_count += 1
            if account:
                try:
                    with self.account_lock:
                        with open("success.txt", "a", encoding="utf-8") as f:
                            f.write(f"{account['tk']}|{account['mk']}\n")
                except: pass
        elif status == "banned":
            self.ban_count += 1
            if account:
                try:
                    with self.account_lock:
                        with open("ban.txt", "a", encoding="utf-8") as f:
                            f.write(f"{account['tk']}|{account['mk']}\n")
                except: pass
        
        # Cập nhật lại file input (xóa những acc đã done)
        self.update_input_file()
        self.after(0, self.refresh_ui)

    def update_input_file(self):
        if not self.input_file_path: return
        try:
            with self.account_lock:
                # Lấy những acc chưa xong
                remaining = [f"{a['tk']}|{a['mk']}\n" for a in self.accounts_data if not a.get('done')]
                with open(self.input_file_path, "w", encoding="utf-8") as f:
                    f.writelines(remaining)
        except Exception as e:
            print(f"Lỗi cập nhật file input: {e}")

    def start_all(self):
        if not self.accounts_data: return
        self.btn_start.configure(state="disabled", text=" ĐANG CHẠY...")
        for a in self.accounts_data: a['processing'] = False
        self.active_workers = []
        for d in self.device_serials:
            w = AutoClickerInstance(d, self.adb_path, print, self.refresh_ui, self.report_stats)
            w.account_lock = self.account_lock
            self.active_workers.append(w)
            threading.Thread(target=w.run, args=(self.accounts_data,), daemon=True).start()

    def stop_all(self):
        for w in self.active_workers: w.running = False
        self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")

if __name__ == "__main__":
    MultiPremiumApp().mainloop()

# pyinstaller --noconfirm --onefile --windowed --name "MegaLoginCF" --add-data "images;images" --add-data "logo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool.py

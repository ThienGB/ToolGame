import json
import time
import os
import subprocess
import threading
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
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- Paths & Constants ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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
    def __init__(self, device_id, adb_path, log_func, update_ui_func, report_stats_func, device_type="LD", restart_threshold=0):
        self.device_id, self.adb_path = device_id, adb_path
        self.log_func, self.update_ui_func, self.report_stats_func = log_func, update_ui_func, report_stats_func
        self.device_type = device_type
        self.running, self.status, self.is_lagging = False, "Đang chờ", False
        self.current_account = None
        self.account_lock = None 
        self.restart_threshold = restart_threshold
        self.fail_streak = 0

    def log(self, msg): self.log_func(f"[{self.device_id}] {msg}")
    
    def call_adb(self, args, timeout=15):
        try:
            res = subprocess.run([self.adb_path, "-s", self.device_id] + args, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
            if b"not found" in res.stderr or b"offline" in res.stderr:
                subprocess.run([self.adb_path, "connect", self.device_id], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                res = subprocess.run([self.adb_path, "-s", self.device_id] + args, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
            return res
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess([], 1, b"", b"timeout")
        except Exception as e:
            return subprocess.CompletedProcess([], 1, b"", str(e).encode())

    def try_connect_port(self, port):
        try:
            subprocess.run([self.adb_path, "connect", f"127.0.0.1:{port}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=0.6, creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass

    def restart_emulator(self):
        self.status = "Đang Restart..."
        self.update_ui_func()
        self.log("RESTART: Đang khởi động lại máy ảo...")
        
        base_path = os.path.dirname(self.adb_path)
        # Ưu tiên các file console CLI
        ld_path = None
        for exe in ["ldconsole.exe", "dnconsole.exe", "ld.exe"]:
            p = os.path.join(base_path, exe)
            if os.path.exists(p):
                ld_path = p
                break
        
        if not ld_path:
            # Dự phòng dnplayer nếu không thấy console (dù khả năng cao sẽ lỗi lệnh)
            ld_path = os.path.join(base_path, "dnplayer.exe")

        try:
            port = int(self.device_id.split(':')[-1]) if ':' in self.device_id else 5554
            idx = (port - 5554) // 2
            
            # 2. Đóng máy ảo
            self.log(f"RESTART: Đang đóng máy ảo index {idx}...")
            subprocess.run([ld_path, "quit", "--index", str(idx)], creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(5)
            
            # 3. Mở lại máy ảo
            self.log(f"RESTART: Đang mở lại máy ảo index {idx}...")
            subprocess.run([ld_path, "launch", "--index", str(idx)], creationflags=subprocess.CREATE_NO_WINDOW)
            # 4. Đợi máy ảo khởi tạo (Hard Sleep)
            self.log("RESTART: Đang đợi máy ảo khởi tạo (10s)...")
            time.sleep(10)
            
            # 5. Đợi khởi động và kiểm tra boot hoàn tất qua ADB
            boot_success = False
            self.log("RESTART: Đang quét trạng thái boot...")
            for i in range(24): # Đợi tối đa 120s (24 * 5s)
                if not self.running: break
                
                # Thử connect lại ADB liên tục
                subprocess.run([self.adb_path, "connect", self.device_id], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                
                # Kiểm tra thuộc tính boot_completed
                check = self.call_adb(["shell", "getprop", "sys.boot_completed"], timeout=5)
                if check.returncode == 0 and "1" in check.stdout.decode().strip():
                    boot_success = True
                    break
                
                self.status = f"Booting ({i*5}s)"
                self.update_ui_func()
                time.sleep(5)

            if not boot_success:
                self.log("RESTART: Quá thời gian chờ (120s). Đang ép làm mới kết nối ADB...")
                # Ngắt kết nối và kết nối lại để ép ADB nhận diện lại thiết bị
                subprocess.run([self.adb_path, "disconnect", self.device_id], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                time.sleep(2)
                subprocess.run([self.adb_path, "connect", self.device_id], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.log("RESTART: Đợi thêm 10s để máy ổn định màn hình...")
                time.sleep(10) 
            else:
                self.log("RESTART: Máy ảo đã báo boot hoàn tất!")
                self.log("RESTART: Đợi thêm 15s để UI ổn định hoàn toàn...")
                time.sleep(15) 
            
            self.status = "Đang chạy"
            self.update_ui_func()
            return True
        except Exception as e:
            self.log(f"RESTART ERROR: {str(e)}")
            self.status = "Lỗi Restart"
            self.update_ui_func()
            return False

    def input_text_robust(self, text):
        if not text: return
        import shlex
        # Tách theo space vì space phải dùng %s trong adb input text
        parts = text.split(' ')
        for i, part in enumerate(parts):
            if part:
                quoted = shlex.quote(part)
                self.call_adb(["shell", "input", "text", quoted])
            if i < len(parts) - 1:
                self.call_adb(["shell", "input", "text", "%s"])

    def clear_input_field(self, delete_count=30):
        # Di chuyển đến cuối và xóa delete_count kí tự trước khi nhập
        self.call_adb(["shell", "input", "keyevent", "123"])
        for _ in range(delete_count):
            self.call_adb(["shell", "input", "keyevent", "67"])

    def input_account_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("tk", "")
        self.clear_input_field()
        self.input_text_robust(content)
        return True

    def input_password_logic(self):
        if not self.current_account: return False
        content = self.current_account.get("mk", "")
        self.clear_input_field()
        self.input_text_robust(content)
        return True

    def escape_adb_text(self, text):
        chars = ['\\', '"', "'", '&', '>', '<', '|', ';', '(', ')', '*', '?', '$', '!', '#', '%', '{', '}', '~', '[', ']', '^', '@']
        return "".join([f"\\{c}" if c in chars else ("%s" if c == ' ' else c) for c in text])

    def execute_step(self, step):
        if not self.running: return False
        action, start = step.get("action"), time.time()
        res = True
        
        if action == "wait":
            time.sleep(step.get("timeout", 1))
        elif action == "click_coords":
            res = self.click_coords_logic(step)
        elif action == "input_account":
            res = self.input_account_logic()
        elif action == "input_password":
            res = self.input_password_logic()
        elif action == "press_esc":
            code = step.get("code", "4") 
            self.call_adb(["shell", "input", "keyevent", str(code)])
            self.log(f"EVENT: Nhấn phím {code}")
        
        self.status, self.is_lagging = "Đang chạy", (time.time() - start) > 35
        self.update_ui_func()
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

    def run(self, accounts):
        self.running = True
        # Cấu hình tọa độ cho từng loại thiết bị
        coords_map = {
            "LD": {
                "user_x": 451, "user_y": 214,
                "pass_x": 473, "pass_y": 258,
                "login_x": 478, "login_y": 307
            },
            "Box": {
                "user_x": 907, "user_y": 440,
                "pass_x": 1012, "pass_y": 525,
                "login_x": 956, "login_y": 606
            }
        }
        
        c = coords_map.get(self.device_type, coords_map["LD"])
        
        self.script = [
            {"action": "click_coords", "x": c["user_x"], "y": c["user_y"], "timeout": 2},
            
            {"action": "input_account"},
            {"action": "click_coords", "x": c["pass_x"], "y": c["pass_y"], "timeout": 2},
            {"action": "input_password"},
            {"action": "click_coords", "x": c["login_x"], "y": c["login_y"], "timeout": 2},
        ]
   
        if self.running:
            target = None
            with self.account_lock:
                target = next((a for a in accounts if not a.get('done') and not a.get('processing')), None)
                if target: target['processing'] = True
            
            if target:
                self.current_account = target
                
                # Vòng lặp "Bất tử": Chỉ thoát khi success=True (về đến bước cuối)
                success = False
                while not success and self.running:
                    self.log(f">> CHẠY: {target['tk']} (Đang cố gắng hoàn thành...)")
                    success = True
                    for step in self.script:
                        if not self.running: break
                        if not self.execute_step(step): 
                            self.log(f"!! LỖI TẠI BƯỚC: {step.get('action')}. Đang quay lại từ đầu...")
                            success = False
                            break
                    
                    if success and self.running:
                        target['done'] = True
                        self.report_stats_func(True)
                        self.update_ui_func()
                        self.log(">> CHÚC MỪNG: Đã về đích thành công (xong 1 vòng).")
                        self.fail_streak = 0 # Reset lỗi khi thành công
                    elif not success and self.running:
                        self.fail_streak += 1
                        self.report_stats_func(False)
                        
                        # Kiểm tra ngưỡng Restart
                        if self.restart_threshold > 0 and self.fail_streak >= self.restart_threshold:
                            self.log(f"!! LAG QUÁ: Lỗi {self.fail_streak} lần. Tiến hành Restart máy ảo...")
                            self.restart_emulator()
                            self.fail_streak = 0 # Reset sau khi restart
                        else:
                            self.log(f">> Đợi 3s để thử lại lượt mới (Thử lại lần {self.fail_streak})...")
                            time.sleep(3)
        self.status = "Xong"; self.update_ui_func(); self.running = False

# --- UI Logic (MultiPremiumApp, LoginApp etc. continue from here) ---
class MultiPremiumApp(ctk.CTk):
    def __init__(self, restart_threshold=0):
        super().__init__()
        self.title("BallisticLogin")
        self.geometry("300x480")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        
        self.accounts_data, self.active_workers = [], []
        self.restart_threshold = 0
        self.account_lock = threading.Lock()
        self.adb_path = self.find_adb()
        self.logo_img = ctk.CTkImage(Image.open(resource_path("mega_login_logo.png")), size=(40, 40))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(20, 20))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(20, 20))

        self.success_count = 0
        self.failure_count = 0
        self.start_timestamp = None

        self.setup_layout()
        self.load_config()
        self.scan_devices()

    def find_adb(self):
        for p in [r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe", "adb"]:
            try:
                subprocess.run([p, "version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return p
            except: continue
        return "adb"
        
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

    def setup_layout(self):
        # Reset and create main container
        for w in self.winfo_children(): w.destroy()
        self.main_f = ctk.CTkFrame(self, fg_color="transparent")
        self.main_f.pack(fill="both", expand=True, padx=8, pady=8)

        # 1. Path & Type (Compact Row)
        cfg_f = ctk.CTkFrame(self.main_f, fg_color=CARD_COLOR, corner_radius=8)
        cfg_f.pack(fill="x", pady=(0, 5))
        
        self.ld_path_entry = ctk.CTkEntry(cfg_f, placeholder_text="Đường dẫn giả lập...", height=28, font=ctk.CTkFont(size=11), fg_color="#333")
        self.ld_path_entry.pack(padx=5, pady=5, fill="x")
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        
        row_type = ctk.CTkFrame(cfg_f, fg_color="transparent")
        row_type.pack(fill="x", padx=5, pady=(0, 5))
        self.device_type_var = ctk.StringVar(value="LD")
        ctk.CTkSegmentedButton(row_type, values=["LD", "Box"], variable=self.device_type_var, command=self.scan_devices, height=24).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(row_type, text="Quét", command=self.save_and_scan, width=50, height=24, fg_color=ACCENT_PURPLE).pack(side="right")

        # 2. Controls
        btn_f = ctk.CTkFrame(self.main_f, fg_color="transparent")
        btn_f.pack(fill="x", pady=5)
        ctk.CTkButton(btn_f, text="Nạp File", command=self.load_file, fg_color="#444", height=32, width=80).pack(side="left")
        self.btn_start = ctk.CTkButton(btn_f, text="CHẠY", command=self.start_all, height=32, fg_color=ACCENT_GREEN)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=5)
        self.btn_stop = ctk.CTkButton(btn_f, text="Dừng", command=self.stop_all, height=32, fg_color="#333", width=60)
        self.btn_stop.pack(side="right")

        # 3. Device List
        dev_card = ctk.CTkFrame(self.main_f, fg_color=CARD_COLOR, corner_radius=8)
        dev_card.pack(fill="both", expand=True, pady=5)
        self.dev_frame = ctk.CTkScrollableFrame(dev_card, height=180, fg_color="transparent")
        self.dev_frame.pack(fill="both", expand=True, padx=2, pady=2)
        self.device_cards = {}
        
        # 4. Simple Stats Row
        stat_f = ctk.CTkFrame(self.main_f, fg_color=CARD_COLOR, corner_radius=8, height=40)
        stat_f.pack(fill="x", pady=(5, 0))
        stat_f.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.devices_val = self.create_mini_stat(stat_f, "Thiết bị", "0", 0, "#A855F7")
        self.success_val = self.create_mini_stat(stat_f, "Xong", "0", 1, "#4ADE80")
        self.progress_val = self.create_mini_stat(stat_f, "Tiến độ", "0/0", 2, "#3B82F6")
        self.fail_val_ui = self.create_mini_stat(stat_f, "Lỗi", "0", 3, ACCENT_RED)

    def create_mini_stat(self, parent, title, value, col, color):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=0, column=col, sticky="nsew")
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=9), text_color="#888").pack()
        lbl = ctk.CTkLabel(f, text=value, font=ctk.CTkFont(size=12, weight="bold"), text_color=color)
        lbl.pack()
        return lbl

    def save_and_scan(self):
        self.save_config()
        self.scan_devices()

    def save_config(self):
        with open("config.json", "w") as f: 
            json.dump({
                "ld_path": self.ld_path_entry.get().strip(),
                "restart_threshold": self.restart_threshold,
                "device_type": self.device_type_var.get()
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
                    self.restart_threshold = int(config.get("restart_threshold", "0"))
                    self.device_type_var.set(config.get("device_type", "LD"))
            except: pass

    def try_connect_port(self, port):
        try:
            subprocess.run([self.adb_path, "connect", f"127.0.0.1:{port}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=0.6, creationflags=subprocess.CREATE_NO_WINDOW)
        except: pass

    def _perform_scan(self):
        p = self.ld_path_entry.get().strip()
        if p.lower().endswith("adb.exe"):
            self.adb_path = p
            base_path = os.path.dirname(p)
        else:
            self.adb_path = os.path.join(p, "adb.exe")
            base_path = p

        if not os.path.exists(self.adb_path):
            self.adb_path = "adb"
        
        device_serials = []
        try:
            device_type = self.device_type_var.get()
            
            if device_type == "LD":
                # 1. Tìm file console điều khiển
                ldconsole_path = None
                for exe in ["ldconsole.exe", "dnconsole.exe", "ld.exe"]:
                    path = os.path.join(base_path, exe)
                    if os.path.exists(path):
                        ldconsole_path = path
                        break
                
                # 2. Lấy danh sách máy ảo đang chạy và connect ADB
                if ldconsole_path:
                    try:
                        res_ld = subprocess.run([ldconsole_path, "list2"], capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                        for line in res_ld.stdout.splitlines():
                            parts = line.split(',')
                            if len(parts) >= 5 and parts[4] == '1': # Chỉ lấy máy ảo đang ON
                                idx = parts[0]
                                port = 5554 + (int(idx) * 2)
                                try:
                                    subprocess.run([self.adb_path, "connect", f"127.0.0.1:{port}"], 
                                                 capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                                except: pass
                    except: pass

                # 3. Quét dự phòng các port phổ biến bằng connect nhanh
                scan_ports = [5554 + (i * 2) for i in range(40)]
                threads = []
                for port in scan_ports:
                    t = threading.Thread(target=self.try_connect_port, args=(port,), daemon=True)
                    t.start()
                    threads.append(t)
                for t in threads:
                    t.join(timeout=1.0)
            else:
                # BoxPhone mode: Làm mới kết nối
                subprocess.run([self.adb_path, "kill-server"], creationflags=subprocess.CREATE_NO_WINDOW)
                subprocess.run([self.adb_path, "start-server"], creationflags=subprocess.CREATE_NO_WINDOW)
            
            # Đợi ADB cập nhật danh sách
            time.sleep(2)

            # 4. Lấy danh sách thiết bị cuối cùng, polling nhanh nếu cần
            for _ in range(3):
                try:
                    res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
                    device_serials = []
                    for line in res.stdout.strip().split('\n')[1:]:
                        if "\tdevice" in line:
                            serial = line.split('\t')[0]
                            if serial not in device_serials:
                                device_serials.append(serial)
                    if device_serials:
                        break
                except: pass
                time.sleep(0.5)
        except Exception as e:
            print(f"SCAN ERROR: {e}")

        # Cập nhật UI trên main thread
        self.after(0, lambda: self._update_device_ui(device_serials))

    def _update_device_ui(self, device_serials):
        for w in self.dev_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        try:
            # Sắp xếp thiết bị dựa trên LD index để thứ tự ổn định
            serials_with_idx = []
            for serial in device_serials:
                abs_idx = self.get_absolute_index(serial)
                serials_with_idx.append((serial, abs_idx))
            
            # Sắp xếp theo index tăng dần
            serials_with_idx.sort(key=lambda x: x[1])
            
            for serial, abs_idx in serials_with_idx:
                card = ctk.CTkFrame(self.dev_frame, fg_color="#333", height=24)
                card.pack(fill="x", pady=1, padx=2)
                card.pack_propagate(False)
                
                display_name = f"[{abs_idx}] {serial.split(':')[-1]}" if abs_idx != -1 else serial
                ctk.CTkLabel(card, text=display_name, font=ctk.CTkFont(size=9), text_color="white").pack(side="left", padx=5)
                
                lbl = ctk.CTkLabel(card, text="Ready", font=ctk.CTkFont(size=8), text_color="#AAA")
                lbl.pack(side="right", padx=5)
                self.device_cards[serial] = {"status": lbl}
        except Exception as e:
            print(f"UI UPDATE ERROR: {e}")
            
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
            total = len(self.accounts_data)
            self.devices_val.configure(text=str(len(self.device_cards)))
            self.success_val.configure(text=str(done))
            self.progress_val.configure(text=f"{done}/{total}")
            self.fail_val_ui.configure(text=str(self.failure_count))
            
            # Nếu tất cả worker đã dừng, mở lại nút Start
            if self.active_workers and all(not w.running for w in self.active_workers):
                self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")
                self.active_workers = []
        except: pass

    def report_stats(self, success, account=None):
        if not success: 
            self.failure_count += 1
        self.after(0, self.refresh_ui)

    def scan_devices(self, _=None):
        threading.Thread(target=self._perform_scan, daemon=True).start()

    def start_all(self):
        if not self.accounts_data: return
        self.btn_start.configure(state="disabled", text=" ĐANG CHẠY...")
        for a in self.accounts_data: a['processing'] = False
        self.active_workers = []
        device_type = self.device_type_var.get()
        for d in self.device_cards.keys():
            w = AutoClickerInstance(d, self.adb_path, print, self.refresh_ui, self.report_stats, device_type=device_type, restart_threshold=self.restart_threshold)
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

# pyinstaller --noconfirm --onefile --windowed --name "MegaLogin" --icon "mega_login_logo.png" --add-data "mega_login_logo.png;." --add-data "start.png;." --add-data "stop.png;." gui_tool_login.py
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
    
    def call_adb(self, args):
        return subprocess.run([self.adb_path, "-s", self.device_id] + args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self):
        try:
            p = self.call_adb(["shell", "screencap", "-p"])
            return cv2.imdecode(np.frombuffer(p.stdout.replace(b"\r\n", b"\n"), np.uint8), cv2.IMREAD_COLOR)
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
        elif action == "press_esc":
            self.call_adb(["shell", "input", "keyevent", "111"])
            self.log("EVENT: Nhấn ESC (Key 111)")
        elif action == "solve_captcha": res = self.solve_captcha_logic(step)
        
        self.status, self.is_lagging = "Đang chạy", (time.time() - start) > 35
        self.update_ui_func()
        return res

    def click_image_logic(self, step):
        targets = [step.get("target")] if step.get("target") else [step.get(f"target{i}") for i in range(1, 6) if step.get(f"target{i}")]
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

    def solve_captcha_logic(self, step):
        sample_roi = step.get("sample_roi")
        grid_roi = step.get("grid_roi")
        rows = step.get("rows", 2)
        cols = step.get("cols", 3)
        confidence = step.get("confidence", 0.25)
        timeout = step.get("timeout_loop", 150) # 150s timeout là đủ, tránh bị kẹt quá lâu
        
        if not sample_roi or not grid_roi:
            self.log("LỖI CAPTCHA: Thiếu sample_roi hoặc grid_roi.")
            return False

        self.log("CAPTCHA: Bắt đầu giải (Đã tối ưu CPU/RAM)...")
        start_loop = time.time()
        
        # Tiền xử lý: Dùng CLAHE để tăng tương phản
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        no_captcha_count = 0
        fail_count = 0

        while time.time() - start_loop < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None: 
                time.sleep(1)
                continue
            
            h, w = screen.shape[:2]
            if w > h:
                self.log("CAPTCHA: Đã quay về màn hình NGANG.")
                del screen
                return True

            # QUAN TRỌNG: Kiểm tra xem nút OK có đang trên màn hình không
            # Nếu không có nút OK trong vài lần check liên tiếp, nghĩa là captcha đã biến mất (đã giải xong)
            ok_template = get_cached_image("images/ok_capcha.png")
            mv_ok = 0
            ml_ok = (0, 0)
            if ok_template is not None:
                res_ok = cv2.matchTemplate(screen, ok_template, cv2.TM_CCOEFF_NORMED)
                _, mv_ok, _, ml_ok = cv2.minMaxLoc(res_ok)
                del res_ok
                if mv_ok < 0.7:
                    no_captcha_count += 1
                    if no_captcha_count >= 3:
                        self.log("CAPTCHA: Không thấy nút OK nữa trên màn hình. Coi như đã giải xong!")
                        del screen
                        return True
                else:
                    no_captcha_count = 0
            else:
                self.log("CẢNH BÁO: Thiếu file images/ok_capcha.png để nhận diện nút OK.")

            # 1. KIỂM TRA DẠNG CAPTCHA BỊ LỖI LỆCH LOẠI
            bad_temp = get_cached_image("images/capcha_order_type.jpg")
            if bad_temp is not None:
                res_bad = cv2.matchTemplate(screen, bad_temp, cv2.TM_CCOEFF_NORMED)
                _, mv_bad, _, _ = cv2.minMaxLoc(res_bad)
                del res_bad
                if mv_bad >= 0.70: # Hạ xuống 0.7 để bắt nhạy hơn
                    self.log(f"CAPTCHA: Phát hiện loại sai ({mv_bad:.2f}). Đang tải hộp thoại mới...")
                    self.call_adb(["shell", "input", "keyevent", "4"])
                    time.sleep(2)
                    self.click_image_logic({"target": "images/get_code.jpg", "timeout": 10, "confidence": 0.8})
                    del screen
                    continue

            try:
                # 2. Trích xuất hình mẫu
                sx, sy, sw, sh = sample_roi
                sx1, sy1 = max(0, sx), max(0, sy)
                sx2, sy2 = min(w, sx+sw), min(h, sy+sh)
                sample_img = screen[sy1:sy2, sx1:sx2].copy()
                
                if sample_img is not None and sample_img.size > 0:
                    sample_gray = cv2.cvtColor(sample_img, cv2.COLOR_BGR2GRAY)
                    sample_enhanced = clahe.apply(sample_gray)
                    sample_enhanced = cv2.GaussianBlur(sample_enhanced, (3, 3), 0)
                    
                    # 3. Chia lưới 
                    gx, gy, gw, gh = grid_roi
                    cell_w, cell_h = gw // cols, gh // rows
                    resized_sample = cv2.resize(sample_enhanced, (cell_w, cell_h))
                    
                    best_val, best_idx = -1, -1
                    total_cells = rows * cols
                    for i in range(total_cells):
                        row_idx, col_idx = i // cols, i % cols
                        cx, cy = gx + col_idx * cell_w, gy + row_idx * cell_h
                        choice_img = screen[cy:cy+cell_h, cx:cx+cell_w]
                        if choice_img is None or choice_img.size == 0: continue
                        
                        choice_gray = cv2.cvtColor(choice_img, cv2.COLOR_BGR2GRAY)
                        choice_enhanced = clahe.apply(choice_gray)
                        choice_enhanced = cv2.GaussianBlur(choice_enhanced, (3, 3), 0)
                        
                        res = cv2.matchTemplate(choice_enhanced, resized_sample, cv2.TM_CCOEFF_NORMED)
                        _, score, _, _ = cv2.minMaxLoc(res)
                        
                        if score > best_val:
                            best_val, best_idx = score, i
                        
                        del res
                        del choice_gray
                        del choice_enhanced

                    # Luôn bấm vào hình có độ khớp cao nhất dù điểm số có thấp, nếu sai game sẽ tự đổi captcha
                    if best_idx != -1:
                        final_row, final_col = best_idx // cols, best_idx % cols
                        tx, ty = gx + final_col * cell_w + cell_w // 2, gy + final_row * cell_h + cell_h // 2
                        self.call_adb(["shell", "input", "tap", str(tx), str(ty)])
                        self.log(f"CAPTCHA: Bấm hình số {best_idx+1} (Khớp: {best_val:.2f})")
                        
                        time.sleep(2)
                        
                        # Táp vào tọa độ nút OK mà ta đã tìm thấy ở đầu loop
                        if ok_template is not None and mv_ok >= 0.7:
                            oh, ow = ok_template.shape[:2]
                            ox, oy = ml_ok[0] + ow//2, ml_ok[1] + oh//2
                            self.call_adb(["shell", "input", "tap", str(ox), str(oy)])
                            self.log("CAPTCHA: Đã bấm nút OK. Đợi phản hồi...")
                    
                    del sample_img
                    del sample_gray
                    del sample_enhanced
                    del resized_sample

                del screen
                time.sleep(3) # Chờ load trạng thái mới
                
            except Exception as e:
                self.log(f"CAPTCHA ERROR: {str(e)}")
                time.sleep(2)
                
        return False
    
    def run(self, accounts):
        self.running = True
        self.script = [
            {"action": "clear_android_data", "package": "com.tencent.stc.cfl"},
            
            {"action": "click_image_if", "target": "images/game_logo.png", "timeout": 5},
            {"action": "click_image", "target": "images/more.png", "timeout": 420},
            {"action": "click_image", "target": "images/lipass.png", "timeout": 120},
            {"action": "click_image", "target": "images/passwordlogin.png", "timeout": 30},
            {"action": "click_image", "target": "images/emailadress.png", "timeout": 120},
            {"action": "input_account_logic"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 10},
            {"action": "click_image", "target": "images/password.png", "timeout": 60},
            {"action": "input_password_logic"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 10},
            {"action": "click_image", "target": "images/login.png", "timeout": 120},
            {"action": "wait", "timeout": 5},
            {"action": "solve_captcha", "sample_roi": [355, 300, 65, 65], "grid_roi": [75, 375, 380, 260]},
            {"action": "click_image_if", "target1": "images/x.png", "target2": "images/x1.png", "timeout": 420},
            {"action": "wait", "timeout": 3},
            {"action": "click_image_if", "target1": "images/x.png", "target2": "images/x1.png", "timeout": 20},
            {"action": "click_image", "target": "images/event_center.jpg", "timeout": 20},
            {"action": "click_image", "target": "images/limited_time.png", "timeout": 20},
            {"action": "click_image", 
              "target1": "images/sk.png",  
              "target2": "images/sk1.png", 
              "target3": "images/invite_friend.png", 
              "target4": "images/invite_friend1.png",
              "target5": "images/invite_friend2.png",
              "target6": "images/invite_friend3.png",
              "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/earn.png", "timeout": 20},
            {"action": "click_image_if", "target": "images/earn.png", "timeout": 3},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/claim.png","timeout": 20},
            {"action": "click_image_if", "target": "images/claim.png","timeout": 5},
            {"action": "click_image_if", "target": "images/claim.png","timeout": 5},
            {"action": "click_image_if", "target": "images/claim.png","timeout": 5},
        ]
        while self.running:
            target = None
            with self.account_lock:
                target = next((a for a in accounts if not a.get('done') and not a.get('processing')), None)
                if target:
                    target['processing'] = True
            
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
                # Nếu lỗi, bỏ flag processing để máy khác hoặc lượt sau có thể thử lại
                with self.account_lock:
                    target['processing'] = False
                self.report_stats_func(False, target)
            time.sleep(5)
        self.status = "Xong"; self.update_ui_func(); self.running = False

# --- Premium UI Part (Copy from MegaUpLvCF style) ---

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
        ctk.CTkLabel(inst_f, text="THIẾT BỊ ĐANG MỞ", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN).pack(pady=10, padx=20, anchor="w")
        self.dev_frame = ctk.CTkScrollableFrame(inst_f, height=180, fg_color="transparent")
        self.dev_frame.pack(fill="x", padx=10, pady=(0, 15))
        for col in range(10): self.dev_frame.grid_columnconfigure(col, weight=1)
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
        with open("config.json", "w") as f: json.dump({"ld_path": self.ld_path_entry.get().strip()}, f)

    def load_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    p = json.load(f).get("ld_path", "")
                    if p: self.ld_path_entry.delete(0, "end"); self.ld_path_entry.insert(0, p)
            except: pass

    def scan_devices(self):
        self.adb_path = os.path.join(self.ld_path_entry.get().strip(), "adb.exe")
        if not os.path.exists(self.adb_path): self.adb_path = "adb"
        for w in self.dev_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        try:
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            devices = [l.split('\t')[0] for l in res.stdout.strip().split('\n')[1:] if "device" in l]
            for i, d in enumerate(devices):
                card = ctk.CTkFrame(self.dev_frame, fg_color="#252525", corner_radius=6, border_width=1, border_color="#383838")
                card.grid(row=i // 10, column=i % 10, padx=3, pady=3, sticky="nsew")
                ctk.CTkLabel(card, text=d.split(":")[-1] if ":" in d else d, font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(5,0))
                lbl = ctk.CTkLabel(card, text="Sẵn sàng", font=ctk.CTkFont(size=9), text_color="#666")
                lbl.pack(pady=(0,5)); self.device_cards[d] = {"status": lbl}
        except: pass

    def load_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if p:
            with open(p, "r", encoding="utf-8") as f:
                for l in f:
                    if "|" in l: tk, mk = l.strip().split("|", 1); self.accounts_data.append({"tk": tk, "mk": mk, "done": False})
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
                            f.write(f"{account['tk']}|{account['mk']}|{datetime.now().strftime('%H:%M:%S')}\n")
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

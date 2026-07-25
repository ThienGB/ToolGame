import os
import sys
import time
import subprocess
import threading
import queue
import numpy as np
import cv2
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog

# Tối ưu cho Windows / Torch
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

ADB_PATH = "adb"
PACKAGE_GARENA = "com.garena.gaslite"  # Tên package app Garena

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#0A0E17"
CARD_COLOR = "#141B2D"
ACCENT_CYAN = "#00D2FF"
ACCENT_GREEN = "#10B981"
ACCENT_RED = "#EF4444"
TEXT_MUTED = "#8B9BB4"


class BoxPhoneControlApp(ctk.CTk):

    def read_items_3_to_5(self, device_id, x1, y1, x2, y2):
        screen = self.get_screenshot(device_id)
        if screen is None:
            return ["Lỗi màn hình", "", ""]

        h_full, w_full = screen.shape[:2]
        
        # Cắt toàn bộ ROI chứa cả 3 item
        crop = screen[max(0, y1):min(h_full, y2), max(0, x1):min(w_full, x2)]
        if crop.size == 0:
            return ["", "", ""]

        # Phóng to x1.5 thay vì x2.5 để giảm chi phí tính toán CPU
        h_c, w_c = crop.shape[:2]
        crop_resized = cv2.resize(crop, (int(w_c * 1.5), int(h_c * 1.5)), interpolation=cv2.INTER_LINEAR)

        if hasattr(self, 'reader') and self.reader is not None:
            try:
                # Đọc 1 LẦN DUY NHẤT cho toàn bộ vùng
                # detail=1 để lấy vị trí (bbox) nhằm phân loại item theo tọa độ X
                results = self.reader.readtext(crop_resized, detail=1, text_threshold=0.5)
                
                width_per_item = crop_resized.shape[1] / 3.0
                items = ["", "", ""]

                for bbox, text, prob in results:
                    # Lấy tọa độ trung tâm X của từ vừa đọc
                    center_x = (bbox[0][0] + bbox[1][0]) / 2.0
                    idx = int(center_x // width_per_item)
                    if 0 <= idx < 3:
                        items[idx] = (items[idx] + " " + text).strip()

                return [item if item else "Không đọc được" for item in items]
            except Exception as e:
                return ["Lỗi OCR", "Lỗi OCR", "Lỗi OCR"]
        else:
            return ["Chưa có EasyOCR"] * 3

    def __init__(self):
        super().__init__()
        self.title("Box Phone Multi-Control Manager")
        self.geometry("1100x820")
        self.configure(fg_color=BG_COLOR)
        
        # Khởi tạo dictionary lưu biến tạm & tài khoản thiết bị
        self.saved_variables = {}
        self.device_accounts = {}

        # Khởi tạo EasyOCR reader
        try:
            import easyocr
            self.reader = easyocr.Reader(['en', 'vi'], gpu=False, verbose=False)
        except Exception as e:
            self.reader = None
            print("Lỗi khởi tạo EasyOCR:", e)

        # Khởi tạo biến dữ liệu & Queue
        self.acc_queue = queue.Queue()          
        self.acc_lock = threading.Lock()        
        
        self.account_file_path = "accounts.txt" 
        self.total_accs = 0
        self.accs_success = 0
        self.accs_remaining = 0
        
        self.adb_path = ADB_PATH
        self.devices = []
        self.is_running = False

        # Tạo file accounts.txt mặc định nếu chưa có
        if not os.path.exists(self.account_file_path):
            with open(self.account_file_path, "w", encoding="utf-8") as f:
                f.write("taikhoan1|matkhau1\ntaikhoan2|matkhau2\n")

        # --- KỊCH BẢN MẪU ---
        self.script_steps = [
            {"type": "MATCH_CLICK", "path": "images/dangnhapgrn.png", "timeout": 600},
            {"type": "INPUT_ACC", "target": "USER"},          
            {"type": "TAP", "x": 221, "y": 630, "delay": 2.0},          
            {"type": "INPUT_ACC", "target": "PASS"},          
            {"type": "TAP", "x": 1733, "y": 553, "delay": 2.0},            
            {"type": "MATCH_CLICK", "path": "images/okdangnhapp.png", "timeout": 15, "optional": False, "retries": 3},
            {"type": "WAIT_IMAGE", "path": "images/tuy_chon.png", "timeout": 20, "threshold": 0.80},
            {"type": "ESC", "delay": 2.0},
            {"type": "ESC", "delay": 2.0},
            {"type": "ESC", "delay": 2.0},
            {
                "type": "WAIT_GAME_WITH_POPUPS",
                "game_path": "images/tuy_chon.png",
                "popup_paths": [
                    "images/vao_tran.png",
                    "images/vaotran.png",
                    "images/x1.png",
                    "images/x3.png",
                    "images/x4.png",
                    "images/x5.png",
                    "images/x6.png",
                    "images/skip.png", 
                    "images/skip1.png",  
                    "images/dkysau.png", 
                    "images/vao.png"
                ]
            },
            {"type": "CLEAR_APP", "package": PACKAGE_GARENA},
            {"type": "ESC", "delay": 2.0},
            
            {"type": "TAP", "x": 1831, "y": 218, "delay": 3.0}, 
            {"type": "TAP", "x": 1831, "y": 218, "delay": 2.0},
            {"type": "TAP", "x": 1831, "y": 218, "delay": 1.0},
            {"type": "TAP", "x": 1831, "y": 218, "delay": 1.0},
            {"type": "MATCH_CLICK", "path": "images/x6.png", "timeout": 3, "optional": True},
            {"type": "MATCH_CLICK", "path": "images/event.png", "timeout": 3, "optional": True},
            {"type": "MATCH_CLICK", "path": "images/x1.png", "timeout": 3, "optional": False, "retries": 3},
            # {"type": "TAP", "x": 233, "y": 424, "delay": 4.0},   # hyt
            {"type": "MATCH_CLICK", "path": "images/hyt.png", "timeout": 8, "optional": False, "retries": 3},
            {"type": "MATCH_CLICK", "path": "images/trung.png", "timeout": 15, "optional": True},
            {"type": "TAP", "x": 1686, "y": 1001, "delay": 2.0},   # nhận
            {"type": "DELAY", "sec": 2.5},
            {"type": "READ_ROI", "x1": 830, "y1": 557, "x2": 1601, "y2": 707, "out_file": "ket_qua_roi.txt"},
            {"type": "TAP", "x": 833, "y": 993, "delay": 2.0}, 
            {"type": "TAP", "x": 80, "y": 57, "delay": 2.0},    # back sk
            {"type": "ESC", "delay": 2.0},
            {"type": "TAP", "x": 1666, "y": 33, "delay": 4.0},   # cài đặt
            {"type": "TAP", "x": 1666, "y": 33, "delay": 1.0},
            {"type": "TAP", "x": 1666, "y": 33, "delay": 1.0},
            {"type": "TAP", "x": 1710, "y": 977, "delay": 2.0},  # log out
            {"type": "MATCH_CLICK", "path": "images/ok_loguot.png", "timeout": 15}
        ]
        
        self.setup_ui()
        self.reload_account_stats()
        self.scan_devices()

    # --- UI LAYOUT ---
    
    def setup_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=290, fg_color=CARD_COLOR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)

        ctk.CTkLabel(self.sidebar, text="BOX PHONE CONTROL", font=ctk.CTkFont(size=18, weight="bold"), text_color=ACCENT_CYAN).pack(pady=(20, 2))
        ctk.CTkLabel(self.sidebar, text="Res: 1080x1920 | Auto Login & Clear", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(0, 5))
        
        self.lbl_dev_count = ctk.CTkLabel(self.sidebar, text="Thiết bị online: 0", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.lbl_dev_count.pack(pady=(0, 15))

        ctk.CTkButton(self.sidebar, text="🔄 Quét Lại ADB", command=self.scan_devices, fg_color="#1E293B", height=32).pack(padx=20, pady=5, fill="x")

        # Quản lý file Accounts
        ctk.CTkLabel(self.sidebar, text="QUẢN LÝ FILE TÀI KHOẢN", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(15, 2))
        ctk.CTkButton(self.sidebar, text="📁 Chọn File Account (.txt)", fg_color="#2563EB", command=self.select_account_file).pack(padx=20, pady=4, fill="x")
        self.lbl_acc_file = ctk.CTkLabel(self.sidebar, text=f"File: {os.path.basename(self.account_file_path)}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED)
        self.lbl_acc_file.pack(pady=(0, 5))

        self.lbl_acc_stats = ctk.CTkLabel(
            self.sidebar, 
            text="Tổng: 0 | Thành công: 0 | Chưa chạy: 0", 
            font=ctk.CTkFont(size=11, weight="bold"), 
            text_color=ACCENT_CYAN
        )
        self.lbl_acc_stats.pack(pady=(0, 10))

        # Cấu hình Vùng ROI
        ctk.CTkLabel(self.sidebar, text="CẤU HÌNH VÙNG ROI ITEM 3->5 (X1, Y1, X2, Y2)", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(12, 5))
        f_roi = ctk.CTkFrame(self.sidebar, fg_color=BG_COLOR)
        f_roi.pack(padx=15, pady=4, fill="x")
        
        self.ent_x1 = ctk.CTkEntry(f_roi, placeholder_text="X1", width=55)
        self.ent_x1.insert(0, "838")
        self.ent_x1.pack(side="left", padx=1, pady=5)

        self.ent_y1 = ctk.CTkEntry(f_roi, placeholder_text="Y1", width=55)
        self.ent_y1.insert(0, "590")
        self.ent_y1.pack(side="left", padx=1, pady=5)

        self.ent_x2 = ctk.CTkEntry(f_roi, placeholder_text="X2", width=55)
        self.ent_x2.insert(0, "1589")
        self.ent_x2.pack(side="left", padx=1, pady=5)

        self.ent_y2 = ctk.CTkEntry(f_roi, placeholder_text="Y2", width=55)
        self.ent_y2.insert(0, "694")
        self.ent_y2.pack(side="left", padx=1, pady=5)

        ctk.CTkButton(self.sidebar, text="👁️ Xem Trước Ảnh Cắt ROI", fg_color="#0284C7", command=self.preview_roi_image).pack(padx=20, pady=5, fill="x")

        # Controls
        self.btn_run = ctk.CTkButton(self.sidebar, text="▶ CHẠY TẤT CẢ MÁY", fg_color=ACCENT_GREEN, height=40, font=ctk.CTkFont(weight="bold"), command=self.start_execution)
        self.btn_run.pack(side="bottom", padx=20, pady=(5, 20), fill="x")

        self.btn_stop = ctk.CTkButton(self.sidebar, text="⏹ DỪNG LẠI", fg_color=ACCENT_RED, height=35, state="disabled", command=self.stop_execution)
        self.btn_stop.pack(side="bottom", padx=20, pady=5, fill="x")

        # Main Workspace
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(self.main_frame, text="NHẬT KÝ THỜI GIAN THỰC", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", pady=(10, 0))
        self.log_box = ctk.CTkTextbox(self.main_frame, fg_color=BG_COLOR, font=ctk.CTkFont(family="Consolas", size=11), text_color="#A8FFB2")
        self.log_box.pack(fill="both", expand=True, pady=5)

    # --- ADB UTILITIES ---
    def call_adb(self, device_id, args):
        cmd = [self.adb_path, "-s", device_id] + args
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    
    def scan_devices(self):
        """Quét danh sách các thiết bị ADB đang online"""
        def _scan():
            self.add_log("🔍 Đang quét danh sách thiết bị ADB...")
            try:
                res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                lines = res.stdout.strip().split('\n')[1:]
                
                devs = []
                for l in lines:
                    parts = l.strip().split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devs.append(parts[0])

                self.devices = list(dict.fromkeys(devs))

                if self.devices:
                    self.add_log(f"✅ Tìm thấy {len(self.devices)} thiết bị online: {', '.join(self.devices)}")
                    if hasattr(self, 'lbl_dev_count'):
                        self.after(0, lambda: self.lbl_dev_count.configure(text=f"Thiết bị online: {len(self.devices)}"))
                else:
                    self.add_log("❌ Không tìm thấy thiết bị ADB nào!")

            except Exception as e:
                self.add_log(f"❌ Lỗi khi quét ADB: {e}")

        threading.Thread(target=_scan, daemon=True).start()

    def get_screenshot(self, device_id):
        try:
            cmd = [self.adb_path, "-s", device_id, "exec-out", "screencap", "-p"]
            proc = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            img_bytes = proc.stdout if proc.returncode == 0 else proc.stdout.replace(b"\r\n", b"\n")
            return cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            return None

    # --- QUẢN LÝ FILE TÀI KHOẢN ---
    def reload_account_stats(self):
        """Đọc file txt và cập nhật thống kê số lượng tài khoản"""
        lines = []
        if os.path.exists(self.account_file_path):
            try:
                with open(self.account_file_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip() and "|" in l]
            except Exception as e:
                self.add_log(f"❌ Lỗi đọc file tài khoản: {e}")

        self.total_accs = len(lines)
        self.accs_remaining = self.total_accs
        self.update_stats_ui()
    
    def update_stats_ui(self):
        text = f"Tổng: {self.total_accs} | Thành công: {self.accs_success} | Chưa chạy: {max(0, self.accs_remaining)}"
        self.lbl_acc_stats.configure(text=text)

    def select_account_file(self):
        file_selected = filedialog.askopenfilename(
            title="Chọn File Tài Khoản TXT",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if file_selected:
            self.account_file_path = file_selected
            self.accs_success = 0
            filename = os.path.basename(file_selected)
            self.lbl_acc_file.configure(text=f"File: {filename}", text_color=ACCENT_CYAN)
            self.reload_account_stats()
            self.add_log(f"📂 Đã chọn file tài khoản: {file_selected}")

    def remove_used_account_from_file(self, file_path, used_username):
        """Xóa dòng chứa account đã chạy xong ra khỏi file txt (Khóa luồng an toàn)"""
        if not os.path.exists(file_path) or not used_username:
            return

        with self.acc_lock:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                for line in lines:
                    parts = line.strip().split("|")
                    if parts and parts[0].strip() != used_username:
                        new_lines.append(line)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                self.add_log(f"🗑️ Đã xóa tài khoản '{used_username}' khỏi file '{os.path.basename(file_path)}'")
                self.reload_account_stats()
            except Exception as e:
                self.add_log(f"❌ Lỗi khi xóa account khỏi file txt: {e}")

    # --- TỰ ĐỘNG HÓA KỊCH BẢN ---
    def handle_popups_until_in_game(self, device_id, game_icon_path, popup_paths, timeout=40):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        start_time = time.time()

        self.add_log(f"[{device_id}] ⏳ Đang chờ 3s tải sảnh & quét dọn Pop-up theo thứ tự...")
        time.sleep(3)

        while time.time() - start_time < timeout:
            if not self.is_running:
                return False

            screen = self.get_screenshot(device_id)
            if screen is None:
                time.sleep(1)
                continue

            popup_clicked = False

            for pop_path in popup_paths:
                full_pop_path = os.path.join(base_dir, os.path.normpath(pop_path))
                if not os.path.exists(full_pop_path):
                    continue

                template_pop = cv2.imread(full_pop_path)
                if template_pop is None:
                    continue

                h, w = template_pop.shape[:2]
                res_pop = cv2.matchTemplate(screen, template_pop, cv2.TM_CCOEFF_NORMED)
                _, max_val_p, _, max_loc_p = cv2.minMaxLoc(res_pop)

                if max_val_p >= 0.85:
                    cx = max_loc_p[0] + w // 2
                    cy = max_loc_p[1] + h // 2
                    
                    self.call_adb(device_id, ["shell", "input", "tap", str(cx), str(cy)])
                    self.add_log(f"[{device_id}] 🧹 [Tắt Pop-up] '{os.path.basename(pop_path)}' ({int(max_val_p*100)}%) ➔ Tap ({cx}, {cy})")
                    
                    popup_clicked = True
                    time.sleep(1.5)
                    break

            if not popup_clicked:
                game_img_path = os.path.join(base_dir, os.path.normpath(game_icon_path))
                if os.path.exists(game_img_path):
                    template_game = cv2.imread(game_img_path)
                    if template_game is not None:
                        res_game = cv2.matchTemplate(screen, template_game, cv2.TM_CCOEFF_NORMED)
                        _, max_val_g, _, _ = cv2.minMaxLoc(res_game)
                        
                        if max_val_g >= 0.80:
                            self.add_log(f"[{device_id}] 🎮 XÁC NHẬN ĐÃ VÀO GAME THÀNH CÔNG! ({int(max_val_g*100)}%)")
                            return True

                time.sleep(0.8)

        self.add_log(f"[{device_id}] ⏱️ Quá {timeout}s chưa thấy Sảnh Game!")
        return False

    def match_and_click(self, device_id, img_name, timeout=10, threshold=0.75, optional=False, retries=3):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(base_dir, os.path.normpath(img_name))

        if not os.path.exists(img_path):
            self.add_log(f"[{device_id}] ❌ Không thấy file ảnh: {img_path}")
            return False

        template = cv2.imread(img_path)
        if template is None:
            self.add_log(f"[{device_id}] ❌ Lỗi đọc file ảnh: {img_name}")
            return False

        h, w = template.shape[:2]
        start_time = time.time()
        click_count = 0

        while time.time() - start_time < timeout:
            if not self.is_running:
                return False

            screen = self.get_screenshot(device_id)
            if screen is not None:
                res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= threshold:
                    click_count += 1
                    center_x = max_loc[0] + w // 2
                    center_y = max_loc[1] + h // 2
                    
                    self.call_adb(device_id, ["shell", "input", "tap", str(center_x), str(center_y)])
                    self.add_log(f"[{device_id}] 🎯 Click '{os.path.basename(img_name)}' (Lần {click_count}/{retries}) ➔ Tap ({center_x}, {center_y})")

                    if optional:
                        return True

                    time.sleep(3.0)

                    screen_after = self.get_screenshot(device_id)
                    if screen_after is not None:
                        res_after = cv2.matchTemplate(screen_after, template, cv2.TM_CCOEFF_NORMED)
                        _, max_val_after, _, _ = cv2.minMaxLoc(res_after)

                        if max_val_after < threshold:
                            self.add_log(f"[{device_id}] ✅ Đã chuyển cảnh thành công! ({os.path.basename(img_name)})")
                            return True

                    if click_count >= retries:
                        self.add_log(f"[{device_id}] ⚠️ Đã click đủ {retries} lần cho ảnh '{os.path.basename(img_name)}', tiếp tục.")
                        return True

            time.sleep(0.8)

        if optional:
            self.add_log(f"[{device_id}] ⏩ Bỏ qua ảnh phụ '{os.path.basename(img_name)}'.")
        else:
            self.add_log(f"[{device_id}] ⏱️ Quá timeout không thấy/xử lý xong: {img_name}")
        return True

    def execute_script_steps(self, device_id):
        """Thực hiện tuần tự tất cả các bước trong self.script_steps"""
        for step in self.script_steps:
            if not self.is_running:
                return False

            st_type = step.get("type")

            if st_type == "MATCH_CLICK":
                self.match_and_click(
                    device_id, 
                    step.get("path"), 
                    timeout=step.get("timeout", 10), 
                    threshold=0.75, 
                    optional=step.get("optional", False),
                    retries=step.get("retries", 3)
                )

            elif st_type == "INPUT_ACC":
                target = step.get("target")
                acc_info = getattr(self, 'device_accounts', {}).get(device_id, {})
                username = acc_info.get("username", "")
                password = acc_info.get("password", "")

                text_to_input = username if target == "USER" else password

                if text_to_input and text_to_input != "N/A":
                    chars_to_escape = [
                        '\\', '"', "'", ' ', '&', '<', '>', '|', ';', '(', ')', 
                        '$', '`', '*', '?', '!', '[', ']', '{', '}', '~', '^', '%'
                    ]
                    
                    clean_text = text_to_input
                    for char in chars_to_escape:
                        clean_text = clean_text.replace(char, f"\\{char}")

                    self.call_adb(device_id, ["shell", "input", "text", clean_text])
                    self.add_log(f"[{device_id}] ⌨️ Nhập {target}: {text_to_input}")
                else:
                    self.add_log(f"[{device_id}] ⚠️ Không có dữ liệu {target} để nhập!")

            elif st_type == "TAP":
                if step.get("delay", 0) > 0:
                    time.sleep(step.get("delay"))
                self.call_adb(device_id, ["shell", "input", "tap", str(step.get("x")), str(step.get("y"))])

            elif st_type == "WAIT_IMAGE":
                img_path_rel = step.get("path")
                timeout = step.get("timeout", 20)
                threshold = step.get("threshold", 0.80)
                
                base_dir = os.path.dirname(os.path.abspath(__file__))
                full_img_path = os.path.join(base_dir, os.path.normpath(img_path_rel))

                self.add_log(f"[{device_id}] ⏳ Đang chờ chuyển cảnh ({os.path.basename(img_path_rel)})...")
                start_wait = time.time()
                loaded_success = False

                if os.path.exists(full_img_path):
                    template_wait = cv2.imread(full_img_path)
                    if template_wait is not None:
                        while time.time() - start_wait < timeout:
                            if not self.is_running:
                                break
                            screen = self.get_screenshot(device_id)
                            if screen is not None:
                                res = cv2.matchTemplate(screen, template_wait, cv2.TM_CCOEFF_NORMED)
                                _, max_val, _, _ = cv2.minMaxLoc(res)
                                if max_val >= threshold:
                                    elapsed = round(time.time() - start_wait, 1)
                                    self.add_log(f"[{device_id}] ✅ Đã chuyển cảnh xong sau {elapsed}s!")
                                    loaded_success = True
                                    break
                            time.sleep(1.0)

                if not loaded_success:
                    self.add_log(f"[{device_id}] ⚠️ Quá timeout {timeout}s chưa thấy ảnh chuyển cảnh, tiếp tục.")

            elif st_type == "WAIT_GAME_WITH_POPUPS":
                in_game_success = self.handle_popups_until_in_game(
                    device_id, 
                    game_icon_path=step.get("game_path"), 
                    popup_paths=step.get("popup_paths", []), 
                    timeout=step.get("timeout", 600)
                )
                if not in_game_success:
                    self.add_log(f"[{device_id}] 🛑 Dừng kịch bản do không vào được game.")
                    return False

            elif st_type == "READ_ROI":
                x1 = step.get("x1", 838)
                y1 = step.get("y1", 590)
                x2 = step.get("x2", 1589)
                y2 = step.get("y2", 694)
                file_name = step.get("out_file", "ket_qua_roi.txt")
                
                self.add_log(f"[{device_id}] 🔍 Đang quét 3 Item (Item 3->5) trong vùng ROI [{x1}, {y1}, {x2}, {y2}]...")
                
                # Nối gọi hàm chia 3 ROI đọc độc lập từng ô
                items = self.read_items_3_to_5(device_id, x1, y1, x2, y2)
                scanned_text = " | ".join(items) if items else "Không đọc được"
                
                self.add_log(f"[{device_id}] 📝 Kết quả đọc 3 Item: '{scanned_text}'")

                acc_info = getattr(self, "device_accounts", {}).get(device_id, {})
                username = acc_info.get("username", "N/A")
                password = acc_info.get("password", "N/A")

                line_data = f"{username}|{password}|{scanned_text}\n"
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    out_path = os.path.join(base_dir, file_name)
                    
                    with open(out_path, "a", encoding="utf-8") as f:
                        f.write(line_data)
                        
                    self.add_log(f"[{device_id}] 💾 Xuất kết quả ra file '{file_name}' thành công!")
                except Exception as e:
                    self.add_log(f"[{device_id}] ❌ Lỗi ghi file .txt: {e}")

            elif st_type == "ESC":
                if step.get("delay", 0) > 0:
                    time.sleep(step.get("delay"))
                self.call_adb(device_id, ["shell", "input", "keyevent", "111"])
                self.add_log(f"[{device_id}] ⌨️ Đã nhấn phím ESC")

            elif st_type == "CLEAR_APP":
                pkg = step.get("package")
                self.call_adb(device_id, ["shell", "pm", "clear", pkg])
                self.add_log(f"[{device_id}] 🧹 Đã xóa dữ liệu ứng dụng: {pkg}")

            elif st_type == "DELAY":
                time.sleep(float(step.get("sec", 1.0)))

        return True

    def run_loop_for_device(self, device_id):
        """Vòng lặp lấy tài khoản từ Queue -> Chạy -> Xóa khỏi file txt"""
        while self.is_running:
            try:
                acc_line = self.acc_queue.get_nowait()
            except queue.Empty:
                self.add_log(f"[{device_id}] 🎉 Đã hết tài khoản trong Queue. Dừng luồng!")
                break

            parts = acc_line.split("|")
            username = parts[0].strip() if len(parts) > 0 else "N/A"
            password = parts[1].strip() if len(parts) > 1 else "N/A"

            self.device_accounts[device_id] = {
                "username": username, 
                "password": password
            }

            self.add_log(f"[{device_id}] 🚀 Bắt đầu kịch bản với Account: {username}")

            script_success = self.execute_script_steps(device_id)

            if not self.is_running:
                break

            if script_success:
                self.accs_success += 1

            self.remove_used_account_from_file(self.account_file_path, username)

            self.add_log(f"[{device_id}] 🔄 Chuẩn bị chuyển sang Account tiếp theo...")
            time.sleep(2)

    def start_execution(self):
        """Khởi chạy các luồng song song cho tất cả các máy ADB bằng Queue"""
        self.add_log("⚡ Đã bấm nút Chạy Kịch Bản...")

        if not getattr(self, 'devices', []):
            self.scan_devices()
            time.sleep(1)

        if not self.devices:
            self.add_log("❌ KHÔNG CÓ THIẾT BỊ ADB NÀO ONLINE!")
            return

        self.acc_queue = queue.Queue()
        if os.path.exists(self.account_file_path):
            with open(self.account_file_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and "|" in l]
                for line in lines:
                    self.acc_queue.put(line)

        if self.acc_queue.empty():
            self.add_log("❌ File tài khoản rỗng hoặc không đúng định dạng!")
            return

        self.is_running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        
        self.add_log(f"🚀 BẮT ĐẦU KÍCH HOẠT {len(self.devices)} LUỒNG CHẠY SONG SONG...")
        
        for dev_id in self.devices:
            self.add_log(f"📌 Tạo luồng lặp cho máy [{dev_id}]")
            t = threading.Thread(
                target=self.run_loop_for_device,
                args=(dev_id,),
                daemon=True
            )
            t.start()

    def stop_execution(self):
        self.is_running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.add_log("🛑 Đã gửi lệnh dừng toàn bộ kịch bản.")

    # --- LOG & UTILS ---
    def preview_roi_image(self):
        if not self.devices:
            self.add_log("❌ Không có thiết bị nào online để chụp ảnh!")
            return
        
        try:
            x1 = int(self.ent_x1.get().strip())
            y1 = int(self.ent_y1.get().strip())
            x2 = int(self.ent_x2.get().strip())
            y2 = int(self.ent_y2.get().strip())
        except Exception:
            self.add_log("❌ Tọa độ ROI nhập vào không đúng định dạng số!")
            return

        device_id = self.devices[0]
        self.add_log(f"📸 Đang chụp màn hình thử từ máy {device_id}...")
        screen = self.get_screenshot(device_id)

        if screen is None:
            self.add_log("❌ Chụp màn hình thất bại!")
            return

        h_full, w_full = screen.shape[:2]
        crop = screen[max(0, y1):min(h_full, y2), max(0, x1):min(w_full, x2)]

        if crop.size == 0:
            self.add_log("❌ Vùng ROI rỗng!")
            return

        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)

        top = ctk.CTkToplevel(self)
        top.title(f"ROI [{x1}, {y1}, {x2}, {y2}] - Máy: {device_id}")
        top.geometry("520x450")
        top.attributes("-topmost", True)

        h, w = crop.shape[:2]
        scale = min(480 / w, 340 / h) if w > 0 and h > 0 else 1.0
        disp_w = max(int(w * scale), 50)
        disp_h = max(int(h * scale), 50)

        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(disp_w, disp_h))
        lbl = ctk.CTkLabel(top, image=ctk_img, text="")
        lbl.pack(expand=True, padx=10, pady=10)

    def add_log(self, msg):
        """Ghi Log ra terminal và Textbox an toàn đa luồng"""
        timestamp = time.strftime("[%H:%M:%S]")
        full_msg = f"{timestamp} {msg}\n"
        print(full_msg.strip())

        def _update_ui():
            try:
                if hasattr(self, 'log_box') and self.log_box:
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", full_msg)
                    self.log_box.see("end")
            except Exception as e:
                print(f"Lỗi ghi log UI: {e}")

        try:
            self.after(0, _update_ui)
        except Exception:
            pass


if __name__ == "__main__":
    app = BoxPhoneControlApp()
    app.mainloop()
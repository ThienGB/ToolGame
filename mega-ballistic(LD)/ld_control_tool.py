import os
import sys
import time
import subprocess
import threading
import queue
import numpy as np
import cv2
import customtkinter as ctk
from tkinter import filedialog

# Cấu hình UI
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#0A0E17"
CARD_COLOR = "#141B2D"
ACCENT_CYAN = "#00D2FF"
ACCENT_GREEN = "#10B981"
ACCENT_RED = "#EF4444"
TEXT_MUTED = "#8B9BB4"

ADB_PATH = "adb"
PACKAGE_GARENA = "com.garena.gaslite"  # Package app Garena Lite / Garena


class LDPlayerControlTool(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("LDPlayer Multi-Control Tool (Lite Version)")
        self.geometry("900x650")
        self.configure(fg_color=BG_COLOR)

        # Quản lý tài khoản & Thiết bị
        self.acc_queue = queue.Queue()
        self.acc_lock = threading.Lock()
        self.device_accounts = {}
        self.devices = []
        self.is_running = False

        self.account_file_path = "accounts.txt"
        self.total_accs = 0
        self.accs_success = 0
        self.accs_remaining = 0

        # Tự tạo file tài khoản mẫu nếu chưa có
        if not os.path.exists(self.account_file_path):
            with open(self.account_file_path, "w", encoding="utf-8") as f:
                f.write("taikhoan1|matkhau1\ntaikhoan2|matkhau2\n")

        # --- DẠNG KỊCH BẢN CHỈ CHỨA 4 TÍNH NĂNG BẠN YÊU CẦU ---
        self.script_steps = [
            # 1. Xóa dữ liệu app Garena trước khi chạy
            {"type": "CLEAR_APP", "package": PACKAGE_GARENA},
            
            # 2. Click hình ảnh nút đăng nhập Garena
            {"type": "MATCH_CLICK", "path": "images/dangnhapgrn.png", "timeout": 15},

            # 3. Đăng nhập (Nhập User, Click Pass, Nhập Pass)
            {"type": "INPUT_ACC", "target": "USER"},
            {"type": "TAP", "x": 221, "y": 630, "delay": 1.0}, # Click ô mật khẩu
            {"type": "INPUT_ACC", "target": "PASS"},
            
            # 4. Click hình ảnh nút xác nhận Đăng Nhập
            {"type": "MATCH_CLICK", "path": "images/okdangnhapp.png", "timeout": 10},

            # 5. Ví dụ Click tọa độ ESC hoặc nút đóng
            {"type": "TAP", "x": 1666, "y": 33, "delay": 2.0},
            
            # 6. Dọn dẹp xóa app sau khi kết thúc
            {"type": "CLEAR_APP", "package": PACKAGE_GARENA}
        ]

        self.setup_ui()
        self.reload_account_stats()
        self.scan_devices()

    # --- UI KHÔNG GIAN LÀM VIỆC ---
    def setup_ui(self):
        # Sidebar điều khiển
        self.sidebar = ctk.CTkFrame(self, width=280, fg_color=CARD_COLOR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y", padx=0, pady=0)

        ctk.CTkLabel(self.sidebar, text="LDPLAYER TOOL", font=ctk.CTkFont(size=20, weight="bold"), text_color=ACCENT_CYAN).pack(pady=(20, 2))
        ctk.CTkLabel(self.sidebar, text="Tối ưu cho Giả Lập LDPlayer", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(pady=(0, 10))

        self.lbl_dev_count = ctk.CTkLabel(self.sidebar, text="Giả lập online: 0", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED)
        self.lbl_dev_count.pack(pady=(0, 10))

        ctk.CTkButton(self.sidebar, text="🔄 Quét Giả Lập LDPlayer", command=self.scan_devices, fg_color="#1E293B", height=32).pack(padx=20, pady=5, fill="x")

        # Quản lý tài khoản
        ctk.CTkLabel(self.sidebar, text="QUẢN LÝ TÀI KHOẢN", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(20, 2))
        ctk.CTkButton(self.sidebar, text="📁 Chọn File Tài Khoản (.txt)", fg_color="#2563EB", command=self.select_account_file).pack(padx=20, pady=5, fill="x")
        self.lbl_acc_file = ctk.CTkLabel(self.sidebar, text=f"File: {os.path.basename(self.account_file_path)}", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED)
        self.lbl_acc_file.pack(pady=(0, 5))

        self.lbl_acc_stats = ctk.CTkLabel(self.sidebar, text="Tổng: 0 | Xong: 0 | Còn: 0", font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_CYAN)
        self.lbl_acc_stats.pack(pady=(0, 10))

        # Điều khiển Chạy / Dừng
        self.btn_run = ctk.CTkButton(self.sidebar, text="▶ BẮT ĐẦU CHẠY", fg_color=ACCENT_GREEN, height=42, font=ctk.CTkFont(weight="bold"), command=self.start_execution)
        self.btn_run.pack(side="bottom", padx=20, pady=(5, 20), fill="x")

        self.btn_stop = ctk.CTkButton(self.sidebar, text="⏹ DỪNG LẠI", fg_color=ACCENT_RED, height=35, state="disabled", command=self.stop_execution)
        self.btn_stop.pack(side="bottom", padx=20, pady=5, fill="x")

        # Khung hiển thị Log
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(side="right", fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(self.main_frame, text="NHẬT KÝ HOẠT ĐỘNG", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_MUTED).pack(anchor="w", pady=(5, 0))
        self.log_box = ctk.CTkTextbox(self.main_frame, fg_color=BG_COLOR, font=ctk.CTkFont(family="Consolas", size=11), text_color="#A8FFB2")
        self.log_box.pack(fill="both", expand=True, pady=5)

    # --- ADB UTILITIES ---
    def call_adb(self, device_id, args):
        cmd = [ADB_PATH, "-s", device_id] + args
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def scan_devices(self):
        """Quét các cổng LDPlayer ADB đang kết nối (ví dụ: emulator-5554, 127.0.0.1:5555,...)"""
        def _scan():
            self.add_log("🔍 Đang quét danh sách LDPlayer ADB...")
            try:
                res = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                lines = res.stdout.strip().split('\n')[1:]

                devs = []
                for l in lines:
                    parts = l.strip().split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devs.append(parts[0])

                self.devices = list(dict.fromkeys(devs))

                if self.devices:
                    self.add_log(f"✅ Tìm thấy {len(self.devices)} giả lập online: {', '.join(self.devices)}")
                    self.after(0, lambda: self.lbl_dev_count.configure(text=f"Giả lập online: {len(self.devices)}"))
                else:
                    self.add_log("❌ Không tìm thấy giả lập LDPlayer nào đang bật ADB!")

            except Exception as e:
                self.add_log(f"❌ Lỗi quét ADB: {e}")

        threading.Thread(target=_scan, daemon=True).start()

    def get_screenshot(self, device_id):
        try:
            cmd = [ADB_PATH, "-s", device_id, "exec-out", "screencap", "-p"]
            proc = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            img_bytes = proc.stdout if proc.returncode == 0 else proc.stdout.replace(b"\r\n", b"\n")
            return cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:
            return None

    # --- QUẢN LÝ TÀI KHOẢN ---
    def reload_account_stats(self):
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
        text = f"Tổng: {self.total_accs} | Xong: {self.accs_success} | Còn: {max(0, self.accs_remaining)}"
        self.lbl_acc_stats.configure(text=text)

    def select_account_file(self):
        file_selected = filedialog.askopenfilename(title="Chọn File Tài Khoản TXT", filetypes=[("Text Files", "*.txt")])
        if file_selected:
            self.account_file_path = file_selected
            self.accs_success = 0
            self.lbl_acc_file.configure(text=f"File: {os.path.basename(file_selected)}", text_color=ACCENT_CYAN)
            self.reload_account_stats()
            self.add_log(f"📂 Đã nạp file tài khoản: {file_selected}")

    def remove_used_account_from_file(self, file_path, used_username):
        if not os.path.exists(file_path) or not used_username:
            return
        with self.acc_lock:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = [l for l in lines if l.strip().split("|")[0].strip() != used_username]
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                self.add_log(f"🗑️ Đã gạt bỏ tài khoản '{used_username}' khỏi file txt")
                self.reload_account_stats()
            except Exception as e:
                self.add_log(f"❌ Lỗi cập nhật file tài khoản: {e}")

    # --- CORE 4 TÍNH NĂNG CHÍNH ---

    def match_and_click(self, device_id, img_name, timeout=10, threshold=0.75):
        """1. CLICK HÌNH ẢNH (MATCH_CLICK)"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(base_dir, os.path.normpath(img_name))

        if not os.path.exists(img_path):
            self.add_log(f"[{device_id}] ❌ Thư mục thiếu ảnh: {img_name}")
            return False

        template = cv2.imread(img_path)
        if template is None:
            return False

        h, w = template.shape[:2]
        start_time = time.time()

        while time.time() - start_time < timeout:
            if not self.is_running:
                return False

            screen = self.get_screenshot(device_id)
            if screen is not None:
                res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)

                if max_val >= threshold:
                    center_x = max_loc[0] + w // 2
                    center_y = max_loc[1] + h // 2
                    self.call_adb(device_id, ["shell", "input", "tap", str(center_x), str(center_y)])
                    self.add_log(f"[{device_id}] 🎯 Tìm thấy '{os.path.basename(img_name)}' ({int(max_val*100)}%) ➔ Click ({center_x}, {center_y})")
                    return True

            time.sleep(0.5)

        self.add_log(f"[{device_id}] ⏱️ Quá {timeout}s không thấy ảnh: {os.path.basename(img_name)}")
        return False

    def execute_script_steps(self, device_id):
        """Xử lý vòng lặp các bước trong Kịch Bản"""
        for step in self.script_steps:
            if not self.is_running:
                return False

            st_type = step.get("type")

            # TÍNH NĂNG 1: CLICK TỌA ĐỘ
            if st_type == "TAP":
                if step.get("delay", 0) > 0:
                    time.sleep(step.get("delay"))
                x, y = step.get("x"), step.get("y")
                self.call_adb(device_id, ["shell", "input", "tap", str(x), str(y)])
                self.add_log(f"[{device_id}] 👆 Click Tọa Độ ({x}, {y})")

            # TÍNH NĂNG 2: CLICK HÌNH ẢNH
            elif st_type == "MATCH_CLICK":
                self.match_and_click(
                    device_id,
                    step.get("path"),
                    timeout=step.get("timeout", 10),
                    threshold=step.get("threshold", 0.75)
                )

            # TÍNH NĂNG 3: NHẬP TÀI KHOẢN (USER / PASS)
            elif st_type == "INPUT_ACC":
                target = step.get("target")
                acc_info = self.device_accounts.get(device_id, {})
                text_to_input = acc_info.get("username", "") if target == "USER" else acc_info.get("password", "")

                if text_to_input:
                    # Escape các ký tự đặc biệt cho ADB command
                    clean_text = text_to_input
                    for char in ['\\', '"', "'", ' ', '&', '<', '>', '|', ';', '(', ')', '$', '`', '*', '?', '!', '[', ']', '{', '}', '~', '^', '%']:
                        clean_text = clean_text.replace(char, f"\\{char}")

                    self.call_adb(device_id, ["shell", "input", "text", clean_text])
                    self.add_log(f"[{device_id}] ⌨️ Đã nhập {target}: {text_to_input}")

            # TÍNH NĂNG 4: XÓA DỮ LIỆU APP GARENA
            elif st_type == "CLEAR_APP":
                pkg = step.get("package", PACKAGE_GARENA)
                self.call_adb(device_id, ["shell", "pm", "clear", pkg])
                self.add_log(f"[{device_id}] 🧹 Đã xóa dữ liệu App (Clear Data): {pkg}")

        return True

    # --- LUỒNG CHẠY ĐA THIẾT BỊ ---
    def run_loop_for_device(self, device_id):
        while self.is_running:
            try:
                acc_line = self.acc_queue.get_nowait()
            except queue.Empty:
                self.add_log(f"[{device_id}] 🎉 Hết tài khoản. Luồng kết thúc!")
                break

            parts = acc_line.split("|")
            username = parts[0].strip() if len(parts) > 0 else ""
            password = parts[1].strip() if len(parts) > 1 else ""

            self.device_accounts[device_id] = {"username": username, "password": password}
            self.add_log(f"[{device_id}] 🚀 Chạy kịch bản cho Account: {username}")

            success = self.execute_script_steps(device_id)

            if success:
                self.accs_success += 1

            self.remove_used_account_from_file(self.account_file_path, username)
            time.sleep(1)

    def start_execution(self):
        if not self.devices:
            self.scan_devices()
            time.sleep(1)

        if not self.devices:
            self.add_log("❌ Chưa phát hiện LDPlayer ADB nào online!")
            return

        self.acc_queue = queue.Queue()
        if os.path.exists(self.account_file_path):
            with open(self.account_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip() and "|" in line:
                        self.acc_queue.put(line.strip())

        if self.acc_queue.empty():
            self.add_log("❌ File tài khoản rỗng!")
            return

        self.is_running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        self.add_log(f"⚡ BẮT ĐẦU KÍCH HOẠT {len(self.devices)} MÁY LDPLAYER CHẠY SONG SONG...")

        for dev_id in self.devices:
            t = threading.Thread(target=self.run_loop_for_device, args=(dev_id,), daemon=True)
            t.start()

    def stop_execution(self):
        self.is_running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.add_log("🛑 Đã gửi lệnh dừng toàn bộ luồng.")

    def add_log(self, msg):
        timestamp = time.strftime("[%H:%M:%S]")
        full_msg = f"{timestamp} {msg}\n"
        print(full_msg.strip())

        def _update_ui():
            try:
                if hasattr(self, 'log_box') and self.log_box:
                    self.log_box.configure(state="normal")
                    self.log_box.insert("end", full_msg)
                    self.log_box.see("end")
            except Exception:
                pass

        self.after(0, _update_ui)


if __name__ == "__main__":
    app = LDPlayerControlTool()
    app.mainloop()
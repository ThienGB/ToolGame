import json
import time
import os
import subprocess
import threading
import random
import string
import cv2
import numpy as np
import customtkinter as ctk
from PIL import Image
from datetime import datetime, timedelta
import sys
import hashlib
import base64
import uuid
import urllib.request
import re
import imaplib
import email
from email.header import decode_header
try:
    import winreg
except ImportError:
    winreg = None


# Hàm hỗ trợ tìm đường dẫn file khi đóng gói .exe
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Security & Licensing ---
SECRET_KEY = "RyoUTE_MegaUpLvCF_2026"
LICENSE_FILE = "license.bin"

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

# Công cụ nhanh cho Admin để tạo Key (Bạn có thể bỏ vào file riêng)
# def generate_key(hwid, days):
#     expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
#     sig = hashlib.sha256(f"{expiry}{hwid}{SECRET_KEY}".encode()).hexdigest()[:10]
#     full_key = base64.b64encode(f"{expiry}|{sig}".encode()).decode()
#     return full_key

# --- Theme Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

NAV_COLOR = "#0F0F0F"
BG_COLOR = "#121212"
CARD_COLOR = "#1D1D1D"
ACCENT_GREEN = "#00D2FF"
ACCENT_PURPLE = "#A855F7"
ACCENT_RED = "#EF4444"

# --- GMAIL DOT TRICK CONFIG ---
GMAIL_USER = "hoangcongthien1612@gmail.com"
GMAIL_PASS = "lztmjrkwhfuwkzii" # Mật khẩu ứng dụng của bạn

# --- Logic Backend (AutoClicker - Hỗ trợ Single Instance) ---

class AutoClickerInstance:
    def __init__(self, device_id, adb_path, log_func, update_ui_func, report_stats_func):
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
        self.codes_queue = [] 
        self.current_code_index = 0
        self.current_email = None
        self.mail_tm_token = None

    def log(self, msg):
        self.log_func(f"[{self.device_id}] {msg}")

    def escape_adb_text(self, text):
        if not text: return ""
        chars_to_escape = ['\\', '"', "'", '&', '>', '<', '|', ';', '(', ')', '*', '?', '$', '!', '#', '%', '{', '}', '~', '[', ']', '^', '@']
        escaped_text = ""
        for char in text:
            if char == ' ': escaped_text += "%s"
            elif char in chars_to_escape: escaped_text += f"\\{char}"
            else: escaped_text += char
        return escaped_text

    def update_status(self, status, is_lagging=False):
        self.status = status
        self.is_lagging = is_lagging
        self.update_ui_func()

    def call_adb(self, args):
        cmd = [self.adb_path, "-s", self.device_id] + args
        # Thêm CREATE_NO_WINDOW để không bị hiện CMD khi chạy trên Win
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self):
        try:
            # Khôi phục lại lệnh shell truyền thống mà bạn đã dùng ổn định trước đó
            cmd = [self.adb_path, "-s", self.device_id, "shell", "screencap", "-p"]
            process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if process.returncode != 0: return None
            # Xử lý ký tự xuống dòng Windows cho dữ liệu ảnh sạch
            image_bytes = process.stdout.replace(b"\r\n", b"\n")
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        except: return None

    def execute_step(self, step):
        if not self.running: return False
        action = step.get("action")
        self.last_step_time = time.time()
        res = True
        
        if action == "click_image":
            res = self.click_image_logic(step)
        elif action == "click_image_if":
            self.click_image_logic(step)
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
        elif action == "search":
            res = self.search_logic(step)
        elif action == "solve_captcha":
            res = self.solve_captcha_logic(step)
        elif action == "press_esc":
            res = self.press_esc_logic(step)
        elif action == "generate_temp_email":
            res = self.generate_temp_email_logic()
        elif action == "input_temp_email":
            res = self.input_temp_email_logic()
        elif action == "wait_for_email_code":
            res = self.wait_for_email_code_logic(step)
        
        # Kiểm tra lag: Nếu 1 bước mất hơn 35s
        duration = time.time() - self.last_step_time
        if duration > 35: 
             self.update_status("Lag", True)
        else:
             self.update_status("Đang chạy", False)

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
                img = cv2.imread(real_path)
                if img is not None: target_imgs.append((t_path, img))
            else:
                self.log(f"LỖI: Không tìm thấy ảnh mẫu: {t_path}")

        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                # Lưu ảnh debug để bạn kiểm tra xem tool nhìn thấy gì (Mỗi máy 1 ảnh)
                cv2.imwrite(f"debug_{self.device_id}.png", screen)
                
                for t_path, t_img in target_imgs:
                    res = cv2.matchTemplate(screen, t_img, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val >= confidence:
                        th, tw = t_img.shape[:2]
                        cx, cy = max_loc[0] + tw//2, max_loc[1] + th//2
                        self.call_adb(["shell", "input", "tap", str(cx), str(cy)])
                        self.log(f"CLICK: {os.path.basename(t_path)} (Khớp: {max_val:.2f})")
                        return True
                    else:
                        # Log nếu điểm số gần đạt để bạn biết lý do nó không click
                        if max_val > 0.4:
                            self.log(f"TRƯỢT: {os.path.basename(t_path)} khớp {max_val:.2f} (Cần {confidence})")
            time.sleep(1)
        return False

    def search_logic(self, step):
        target = step.get("target")
        timeout = step.get("timeout", 10)
        conf = step.get("confidence", 0.8)
        
        real_path = resource_path(target)
        if not os.path.exists(real_path): return False
        t_img = cv2.imread(real_path)
        if t_img is None: return False
        start = time.time()
        while time.time() - start < timeout and self.running:
            screen = self.get_screenshot()
            if screen is not None:
                res = cv2.matchTemplate(screen, t_img, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val >= conf:
                    self.log(f"TÌM THẤY: {os.path.basename(target)} (Khớp: {max_val:.2f})")
                    return True
                
                # Log phụ nếu không tìm thấy cho hành động Search
                if max_val > 0.4:
                    self.log(f"SEARCH: {os.path.basename(target)} khớp {max_val:.2f}")
            time.sleep(1)
        return False

    def solve_captcha_logic(self, step):
        sample_roi = step.get("sample_roi")
        grid_roi = step.get("grid_roi")
        rows = step.get("rows", 2)
        cols = step.get("cols", 3)
        confidence = step.get("confidence", 0.3)
        timeout = step.get("timeout_loop", 300) 

        if not sample_roi or not grid_roi:
            self.log("LỖI CAPTCHA: Thiếu sample_roi hoặc grid_roi.")
            return False

        self.log("CAPTCHA: Bắt đầu chu kỳ tìm và chọn hình...")
        start_loop = time.time()
        
        while time.time() - start_loop < timeout and self.running:
            screen = self.get_screenshot()
            if screen is None: break
            
            h, w = screen.shape[:2]
            # Nếu màn hình đã về hướng NGANG -> Coi như đã giải xong hoặc trình duyệt đã đóng
            if w > h:
                self.log("CAPTCHA: Đã quay về màn hình NGANG. Kết thúc bước giải.")
                return True

            try:
                # 1. Trích xuất hình mẫu (Cắt ảnh an toàn)
                sx, sy, sw, sh = sample_roi
                sx1, sy1 = max(0, sx), max(0, sy)
                sx2, sy2 = min(w, sx+sw), min(h, sy+sh)
                sample_img = screen[sy1:sy2, sx1:sx2]
                
                if sample_img is not None and sample_img.size > 0:
                    cv2.imwrite(f"debug_sample_{self.device_id}.png", sample_img)
                    sample_gray = cv2.cvtColor(sample_img, cv2.COLOR_BGR2GRAY)
                    
                    # 2. Chia lưới và tìm hình khớp nhất
                    gx, gy, gw, gh = grid_roi
                    cell_w, cell_h = gw // cols, gh // rows
                    
                    # Lưu ảnh vùng lưới để debug
                    grid_view = screen[gy:gy+gh, gx:gx+gw]
                    cv2.imwrite(f"debug_grid_{self.device_id}.png", grid_view)
                    
                    # Resize mẫu 1 lần duy nhất
                    resized_sample = cv2.resize(sample_gray, (cell_w, cell_h))
                    
                    best_val, best_idx = -1, -1
                    scores = []
                    
                    total_cells = rows * cols
                    for i in range(total_cells):
                        row_idx, col_idx = i // cols, i % cols
                        cx, cy = gx + col_idx * cell_w, gy + row_idx * cell_h
                        choice_img = screen[cy:cy+cell_h, cx:cx+cell_w]
                        if choice_img is None or choice_img.size == 0: continue
                        
                        choice_gray = cv2.cvtColor(choice_img, cv2.COLOR_BGR2GRAY)
                        res = cv2.matchTemplate(choice_gray, resized_sample, cv2.TM_CCOEFF_NORMED)
                        _, max_val, _, _ = cv2.minMaxLoc(res)
                        scores.append(f"{i+1}:{max_val:.2f}")
                        if max_val > best_val:
                            best_val, best_idx = max_val, i
                    
                    self.log(f"CAPTCHA SCORE: {' | '.join(scores)}")
                    
                    if best_idx != -1:
                        # 1. Click chọn hình (Luôn chọn thằng cao nhất)
                        final_row, final_col = best_idx // cols, best_idx % cols
                        tx, ty = gx + final_col * cell_w + cell_w // 2, gy + final_row * cell_h + cell_h // 2
                        self.call_adb(["shell", "input", "tap", str(tx), str(ty)])
                        self.log(f"CAPTCHA: Đã chọn hình {best_idx+1} (Khớp: {best_val:.2f})")
                        
                        # 2. Tìm và nhấn nút OK bằng hình ảnh ok_capcha.png
                        time.sleep(2)
                        ok_path = resource_path("images/ok_capcha.png")
                        if os.path.exists(ok_path):
                            ok_template = cv2.imread(ok_path)
                            if ok_template is not None:
                                scr_ok = self.get_screenshot()
                                if scr_ok is not None:
                                    res_ok = cv2.matchTemplate(scr_ok, ok_template, cv2.TM_CCOEFF_NORMED)
                                    _, mv_ok, _, ml_ok = cv2.minMaxLoc(res_ok)
                                    if mv_ok >= 0.8:
                                        oh, ow = ok_template.shape[:2]
                                        ox, oy = ml_ok[0] + ow//2, ml_ok[1] + oh//2
                                        self.call_adb(["shell", "input", "tap", str(ox), str(oy)])
                                        self.log(f"CAPTCHA: Đã nhấn nút OK (Khớp: {mv_ok:.2f})")
                
                time.sleep(4)
                
            except Exception as e:
                time.sleep(2)
        
        return False

    def press_esc_logic(self, step):
        wait_time = step.get("wait", 0)
        if wait_time > 0: time.sleep(wait_time)
        # Sử dụng keyevent 4 (Back/ESC) phổ biến cho game mobile
        self.call_adb(["shell", "input", "keyevent", "4"])
        self.log(f"KEY: Đã bấm ESC (Gửi keyevent 4, chờ {wait_time}s)")
        return True

    def generate_temp_email_logic(self):
        try:
            # Gmail Dot Trick Implementation
            user_part, domain_part = GMAIL_USER.split('@')
            
            # Chọn ngẫu nhiên số lượng dấu chấm và vị trí (không ở đầu/cuối/cạnh nhau)
            # Một cách đơn giản: tung đồng xu cho mỗi khoảng trống giữa các chữ cái
            while True:
                new_user = ""
                for i in range(len(user_part) - 1):
                    new_user += user_part[i]
                    if random.choice([True, False]):
                        new_user += "."
                new_user += user_part[-1]
                
                # Đảm bảo không trùng với mail gốc (tùy chọn)
                if new_user != user_part:
                    self.current_email = f"{new_user}@{domain_part}"
                    break
                    
            self.log(f"GMAIL DOT: Đã tạo mail con: {self.current_email}")
            return True
        except Exception as e:
            self.log(f"LỖI TẠO GMAIL: {str(e)}")
            return False

    def input_temp_email_logic(self):
        if not self.current_email:
            if not self.generate_temp_email_logic(): return False
        
        # Xóa trắng trước khi nhập
        for _ in range(40): self.call_adb(["shell", "input", "keyevent", "67"])
        escaped_email = self.escape_adb_text(self.current_email)
        self.call_adb(["shell", "input", "text", escaped_email])
        self.log(f"EMAIL: Đã nhập {self.current_email}")
        return True

    def wait_for_email_code_logic(self, step):
        if not self.current_email: 
            self.log("LỖI: Chưa có Email.")
            return False
        
        timeout = step.get("timeout", 180) 
        self.log(f"GMAIL SEARCH: Đang lùng mã cho [{self.current_email}] ở Inbox, Spam & Quảng cáo...")
        
        start_time = time.time()
        while time.time() - start_time < timeout and self.running:
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(GMAIL_USER, GMAIL_PASS)
                
                # Quét mọi ngõ ngách: Inbox, Spam, Quảng cáo, Tất cả thư
                # Gmail dùng tên quốc tế [Gmail]/...
                folders = ["INBOX", "[Gmail]/Promotions", "[Gmail]/Spam", "[Gmail]/All Mail"]
                code_found = None
                
                for fld in folders:
                    try:
                        status, _ = mail.select(fld, readonly=True)
                        if status != 'OK': 
                            # Dự phòng cho Gmail tiếng Việt
                            if "Promotions" in fld: mail.select('"[Gmail]/Quảng cáo"', readonly=True)
                            elif "Spam" in fld: mail.select('"[Gmail]/Thư rác"', readonly=True)
                            elif "All Mail" in fld: mail.select('"[Gmail]/Tất cả Thư"', readonly=True)
                        
                        # Tìm thư gửi đến mail ảo này hoặc từ Level Infinite
                        typ, msg_ids = mail.search(None, f'(TO "{self.current_email}")')
                        if typ != 'OK' or not msg_ids[0]:
                            typ, msg_ids = mail.search(None, '(FROM "levelinfinite.com" UNSEEN)')
                            
                        if typ == 'OK' and msg_ids[0]:
                            for num in reversed(msg_ids[0].split()):
                                typ, data = mail.fetch(num, '(RFC822)')
                                if typ != 'OK': continue
                                
                                msg = email.message_from_bytes(data[0][1])
                                sender = str(msg.get("From", "")).lower()
                                subject = str(msg.get("Subject", "")).lower()
                                
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() == "text/plain":
                                            body = part.get_payload(decode=True).decode()
                                            break
                                else:
                                    body = msg.get_payload(decode=True).decode()
                                
                                # Tìm mã OTP 5 chữ số (Ưu tiên Level Infinite)
                                import re
                                text_to_check = f"{subject} {body}"
                                codes = re.findall(r'\b\d{5}\b', text_to_check)
                                if not codes: codes = re.findall(r'\b\d{4,6}\b', text_to_check)
                                
                                if codes:
                                    code_found = codes[-1]
                                    break
                        if code_found: break
                    except: continue
                
                if code_found:
                    self.log(f"GMAIL: Đã lấy được mã OTP ({code_found})")
                    self.current_otp = code_found
                    # Xóa trắng ô nhập code (nhấn lùi 10 lần)
                    for _ in range(10): self.call_adb(["shell", "input", "keyevent", "67"])
                    self.call_adb(["shell", "input", "text", code_found])
                    mail.logout()
                    return True
                
                mail.logout()
                time.sleep(15) 
            except Exception as e:
                self.log(f"CHỜ MAIL: {str(e)}")
                time.sleep(10)
        
        return False


    def input_name_logic(self):
        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 20)
        name = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(7)) + ''.join(random.choice("!@#%&*+-") for _ in range(3))
        escaped_name = self.escape_adb_text(name)
        self.call_adb(["shell", "input", "text", escaped_name])
        return True

    def input_text_logic(self, step):
        content = step.get("content", "")
        # Chỉ lấy mã từ danh sách Giftcode nếu từ khóa nội dung là USE_GIFTCODE
        if content == "USE_GIFTCODE":
            if self.codes_queue and self.current_code_index < len(self.codes_queue):
                current_item = self.codes_queue[self.current_code_index]
                if current_item['count'] > 0:
                    content = current_item['code']
                else: return False
            else: return False

        self.call_adb(["shell", "input", "keyevent"] + ["67"] * 35)
        escaped_content = self.escape_adb_text(content)
        self.call_adb(["shell", "input", "text", escaped_content])
        return True

    def run(self, codes):
        self.codes_queue = codes
        self.current_code_index = 0
        self.running = True
        
        # BẢO MẬT: Nhúng kịch bản mới nhất từ script.json
        self.script = [
            {"action": "clear_android_data", "package": "com.tencent.stc.cfl"},
            {"action": "click_image", "target": "images/game_logo.png", "timeout": 30, "confidence": 0.8},
            {"action": "click_image", "target": "images/guest.png", "timeout": 420, "confidence": 0.9},
            {"action": "click_image", "target1": "images/agree.png","target2": "images/agree1.png", "timeout": 60, "confidence": 0.9},
            {"action": "click_image", "target": "images/agree_btn.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/name_input1.png", "timeout": 120, "confidence": 0.9},
            {"action": "click_image", "target": "images/name_input2.png", "timeout": 30, "confidence": 0.9},
            {"action": "input_name", "timeout": 120},
            {"action": "click_image", "target": "images/name_input1.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_name_btn.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/veteran.png", "timeout": 200, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_name_btn.png", "timeout": 30, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 200, "confidence": 0.9},
            {"action": "click_image", "target1": "images/setting.png", "target2": "images/setting1.png", "target3": "images/setting2.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit_btn.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_name_btn.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/key_binding.png", "timeout": 400, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_name_btn.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target1": "images/inventory.png", "target2": "images/inventory1.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/equip.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target1": "images/slot_3.png", "target2": "images/slot_3(2).jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/quick_equip.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit_inventory.png", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 5},
            {"action": "click_image", "target": "images/random_map5.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target1": "images/match.png", "target2": "images/match1.png", "target3": "images/match2.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/any_where.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/close_event.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/supply.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/skip_animation.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/draw_free.png", "timeout": 20, "confidence": 0.9},
            {"action": "search", "target": "images/exp.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_draw.png", "timeout": 200, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit.png", "timeout": 10, "confidence": 0.9},
            {"action": "click_image", "target": "images/close_event.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/inventory2.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/cancel.png", "timeout": 10, "confidence": 0.9},
            {"action": "click_image", "target": "images/items.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/search.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/name_input2.png", "timeout": 20, "confidence": 0.9},
            {"action": "input_text", "content": "card"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.9},
            {"action": "search", "target": "images/5.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/5.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/use_all.jpg", "timeout": 10, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/use.jpg", "timeout": 10, "confidence": 0.9},
            {"action": "click_image", "target": "images/exit1.jpg", "timeout": 60, "confidence": 0.9},
            {"action": "click_image", "target": "images/event_center.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/limited_time.png", "timeout": 20, "confidence": 0.9},
             {"action": "click_image", "target": "images/invite.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/input_code.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/name_input2.png", "timeout": 20, "confidence": 0.9},
            {"action": "input_text", "content": "USE_GIFTCODE"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_invite.png", "timeout": 20, "confidence": 0.9},
            {"action": "press_esc", "wait": 1},

            {"action": "click_image", "target": "images/setting.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/other.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/link_account.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/lipass.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/link_btn.png", "timeout": 10, "confidence": 0.9},
  
            {"action": "click_image", "target": "images/email_input.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "input_temp_email"},
            {"action": "click_image", "target": "images/get_code.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/get_code.jpg", "timeout": 20, "confidence": 0.9},   
            {"action": "wait", "timeout": 5},
            {"action": "solve_captcha",
                "sample_roi": [355, 300, 65, 65],
                "grid_roi": [75, 375, 380, 260],
                "rows": 2,
                "cols": 3,
                "ok_target": [400, 610],
                "confidence": 0.35
            },
            {"action": "click_image", "target": "images/email_validation_code.jpg", "timeout": 20, "confidence": 0.8},
            {"action": "wait_for_email_code", "timeout": 120},
            {"action": "click_image", "target": "images/link.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image_if", "target": "images/link.jpg", "timeout": 5, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_check.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "click_image", "target": "images/confirm_btn.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 2},
            {"action": "click_image", "target": "images/confirm_btn.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/set_password.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "click_image", "target": "images/get_code.jpg", "timeout": 20, "confidence": 0.9},
            {"action": "wait", "timeout": 3},
            {"action": "solve_captcha",
                "sample_roi": [355, 300, 65, 65],
                "grid_roi": [75, 375, 380, 260],
                "rows": 2,
                "cols": 3,
                "ok_target": [400, 610],
                "confidence": 0.35
            },
            {"action": "click_image", "target": "images/email_validation_code.jpg", "timeout": 20, "confidence": 0.8},
            {"action": "wait_for_email_code", "timeout": 120},
            {"action": "click_image_if", "target": "images/ok.png", "timeout": 5, "confidence": 0.8},
            {"action": "click_image", "target": "images/new_password_input.jpg", "timeout": 20, "confidence": 0.8},
            {"action": "input_text", "content": "123456Aa"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.8},
            {"action": "click_image", "target": "images/confirm_new_pass_input.jpg", "timeout": 20, "confidence": 0.8},
            {"action": "input_text", "content": "123456Aa"},
            {"action": "click_image", "target": "images/ok.png", "timeout": 20, "confidence": 0.8},
            {"action": "click_image", "target": "images/confirm_btn.jpg", "timeout": 20, "confidence": 0.8},
        ]

        while self.running:
            # Tìm mã còn lượt
            found_valid_code = False
            for idx, c_item in enumerate(self.codes_queue):
                if c_item['count'] > 0:
                    self.current_code_index = idx
                    found_valid_code = True
                    break
            
            if not found_valid_code:
                self.log("ĐÃ XỬ LÝ XONG TẤT CẢ MÃ.")
                self.running = False
                break
                
            current_item = self.codes_queue[self.current_code_index]
            self.log(f">> BẮT ĐẦU VÒNG: Mã {current_item['code']} (Đang chạy...)")
            
            # Reset dữ liệu cho acc mới và sinh ngay Email ảo
            self.current_email = None
            self.current_otp = None
            self.generate_temp_email_logic() # Sinh ngay email ảo cho vòng này
            self.log(f"ACC LOOP: Email ảo cho vòng này: {self.current_email}")
            
            success = True
            for step in self.script:
                if not self.running: break
                if not self.execute_step(step):
                    self.log("THẤT BẠI: Quá thời gian. Đang thử lại...")
                    success = False
                    break
            
            if success and self.running:
                self.log(f">> THÀNH CÔNG: Email {self.current_email} đã hoàn tất.")
                with threading.Lock():
                    with open("SUCCESS_ACC.txt", "a") as f:
                        f.write(f"{self.current_email}|123456Aa\n")
                    current_item['count'] -= 1
                
                self.report_stats_func(True)
                self.update_ui_func()
            elif not success and self.running:
                self.log(f"!! THẤT BẠI: Mã {current_item['code']} không hoàn tất.")
                self.report_stats_func(False)
            
            time.sleep(5)
        
        self.update_status("Xong")
        self.running = False

# --- Modern UI (Premium Edition) ---

class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvCFTool(LD)")
        self.geometry("1100x850")
        self.configure(fg_color=BG_COLOR)
        
        self.codes_data = [] 
        self.instances = [] # Danh sách các máy thực tế đang chạy ADB
        self.active_workers = [] # Các thread đang chạy
        self.adb_path = self.find_adb()
        self.ld_path = r"C:\LDPlayer\LDPlayer9\ldconsole.exe" # Mặc định
        
        # Stats Data
        self.success_count = 0
        self.failure_count = 0
        self.start_timestamp = None

        # Assets (Sử dụng resource_path để đóng gói)
        self.logo_img = ctk.CTkImage(Image.open(resource_path("logo.png")), size=(80, 80))
        self.start_icon = ctk.CTkImage(Image.open(resource_path("start.png")), size=(25, 25))
        self.stop_icon = ctk.CTkImage(Image.open(resource_path("stop.png")), size=(25, 25))

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
        # 1. Sidebar
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=NAV_COLOR)
        self.sidebar.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.sidebar, image=self.logo_img, text="").pack(pady=(40,0))
        self.logo_label = ctk.CTkLabel(self.sidebar, text="BẢNG ĐIỀU KHIỂN", font=ctk.CTkFont(size=22, weight="bold"), text_color=ACCENT_GREEN)
        self.logo_label.pack(pady=(20, 0))
        ctk.CTkLabel(self.sidebar, text="MegaUpLvCFTool(LD) v2.5", font=ctk.CTkFont(size=12)).pack(pady=(0, 20))

        # LDPlayer Path Config
        self.path_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10)
        self.path_card.pack(padx=20, pady=5, fill="x")
        ctk.CTkLabel(self.path_card, text="ĐƯỜNG DẪN LDPLAYER", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(5, 0))
        self.ld_path_entry = ctk.CTkEntry(self.path_card, placeholder_text="Ví dụ: C:\LDPlayer\LDPlayer9", height=30)
        self.ld_path_entry.pack(padx=10, pady=5, fill="x")
        # Nạp đường dẫn mặc định hoặc từ file cấu hình nếu có
        self.ld_path_entry.insert(0, r"C:\LDPlayer\LDPlayer9")
        ctk.CTkButton(self.path_card, text="Lưu Đường Dẫn", command=self.save_config, height=25).pack(padx=10, pady=5, fill="x")


        # Input Card
        self.input_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333333")
        self.input_card.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(self.input_card, text="THÊM MÃ GIFTCODE", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.code_input = ctk.CTkEntry(self.input_card, placeholder_text="Mã Code...", height=35)
        self.code_input.pack(padx=15, pady=5, fill="x")
        self.count_input = ctk.CTkEntry(self.input_card, placeholder_text="Số lượt...", height=35)
        self.count_input.pack(padx=15, pady=5, fill="x")
        self.count_input.insert(0, "10")
        ctk.CTkButton(self.input_card, text="THÊM VÀO LIST", command=self.add_item, fg_color=ACCENT_PURPLE, height=35).pack(padx=15, pady=10, fill="x")

        # Control
        self.btn_start = ctk.CTkButton(self.sidebar, text=" CHẠY TẤT CẢ", image=self.start_icon, compound="left", command=self.start_all, height=50, corner_radius=10, font=ctk.CTkFont(size=16, weight="bold"))
        self.btn_start.pack(padx=20, pady=(30, 10), fill="x")
        self.btn_stop = ctk.CTkButton(self.sidebar, text=" DỪNG TẤT CẢ", image=self.stop_icon, compound="left", command=self.stop_all, fg_color="#333", height=50, corner_radius=10)
        self.btn_stop.pack(padx=20, pady=10, fill="x")

        # Credit Footer
        ctk.CTkLabel(self.sidebar, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=11), text_color="#666").pack(side="bottom", pady=20)

        # 2. Main Area
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.pack(side="right", fill="both", expand=True, padx=25, pady=25)

        # Instance Selection Card
        self.inst_frame = ctk.CTkFrame(self.main_content, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333")
        self.inst_frame.pack(fill="x", pady=(0, 20))
        inst_header = ctk.CTkFrame(self.inst_frame, fg_color="transparent")
        inst_header.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(inst_header, text="THIẾT BỊ ĐANG MỞ", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN).pack(side="left")

        # Action Buttons for Instances
        btns_frame = ctk.CTkFrame(inst_header, fg_color="transparent")
        btns_frame.pack(side="right")
        # Nút chọn tất cả được gỡ bỏ vì người dùng muốn chạy tất cả máy mà không cần check
        ctk.CTkButton(btns_frame, text="Làm Mới Danh Sách", command=self.scan_devices, height=26, width=120, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=5)

        self.device_list_frame = ctk.CTkScrollableFrame(self.inst_frame, height=180, fg_color="transparent") 
        self.device_list_frame.pack(fill="x", padx=10, pady=(0, 15))
        # Tăng số cột lên 10 để thu gọn cho nhiều máy
        for col in range(10): 
            self.device_list_frame.grid_columnconfigure(col, weight=1)
        self.device_cards = {}


        # Queue and Logs
        self.mid_grid = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.mid_grid.pack(fill="both", expand=True)
        self.mid_grid.grid_columnconfigure((0, 1), weight=1)
        self.mid_grid.grid_rowconfigure(0, weight=1) # Stats/Queue
        self.mid_grid.grid_rowconfigure(1, weight=1) # Log

        # Stats Card (Left side now as requested "log bên trái")
        self.stats_card = ctk.CTkFrame(self.mid_grid, fg_color=CARD_COLOR, corner_radius=15)
        self.stats_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(self.stats_card, text="THÔNG SỐ HOẠT ĐỘNG", font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_GREEN).pack(pady=15)
        
        self.stats_inner = ctk.CTkFrame(self.stats_card, fg_color="transparent")
        self.stats_inner.pack(fill="both", expand=True, padx=20)
        self.stats_inner.columnconfigure((0, 1, 2), weight=1)
        self.stats_inner.rowconfigure((0, 1), weight=1)

        self.total_device_val = self.create_stat_item(self.stats_inner, "TỔNG MÁY", "0", 0, 0, ACCENT_GREEN)
        self.active_device_val = self.create_stat_item(self.stats_inner, "HOẠT ĐỘNG", "0", 0, 1, ACCENT_PURPLE)
        self.inactive_device_val = self.create_stat_item(self.stats_inner, "KHÔNG CHẠY", "0", 0, 2, "#888888")
        
        self.success_val = self.create_stat_item(self.stats_inner, "THÀNH CÔNG", "0", 1, 0, "#4ADE80")
        self.lag_val = self.create_stat_item(self.stats_inner, "ĐANG LAG", "0", 1, 1, "#FB923C")
        self.rem_val = self.create_stat_item(self.stats_inner, "CÒN LẠI", "0", 1, 2, ACCENT_PURPLE)


        # Queue Card (Right side)
        self.queue_card = ctk.CTkFrame(self.mid_grid, fg_color=CARD_COLOR, corner_radius=15)
        self.queue_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.queue_card, text="MÃ GIFTCODE ĐANG CHỜ", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.scroll_q = ctk.CTkScrollableFrame(self.queue_card, fg_color="transparent")
        self.scroll_q.pack(fill="both", expand=True)

        # Log Card (Full width at bottom row)
        self.log_card = ctk.CTkFrame(self.mid_grid, fg_color=CARD_COLOR, corner_radius=15)
        self.log_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(15, 0))
        ctk.CTkLabel(self.log_card, text="NHẬT KÝ HOẠT ĐỘNG", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.log_box = ctk.CTkTextbox(self.log_card, fg_color="#000", font=("Consolas", 11), text_color="#AAA")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_box.configure(state="disabled")

    def create_stat_item(self, parent, title, value, row, col, color):
        frame = ctk.CTkFrame(parent, fg_color="#252525", corner_radius=12)
        frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color="#888").pack(pady=(15, 0))
        val_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
        val_label.pack(pady=(5, 15))
        return val_label

    def report_stats(self, success=True):
        def _update():
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
            self.update_stats_ui()
        self.after(0, _update)

    def update_stats_ui(self):
        self.success_val.configure(text=str(self.success_count))
        total_rem = sum(item["count"] for item in self.codes_data)
        self.rem_val.configure(text=str(total_rem))
        
        # New stats
        total_devices = len(self.device_cards)
        self.total_device_val.configure(text=str(total_devices))
        
        active = sum(1 for w in self.active_workers if w.running)
        self.active_device_val.configure(text=str(active))
        
        inactive = total_devices - active
        self.inactive_device_val.configure(text=str(inactive))
        
        lags = sum(1 for w in self.active_workers if w.is_lagging)
        self.lag_val.configure(text=str(lags))

    def update_all_ui(self):
        def _update():
            # Cập nhật danh sách giftcode
            self.refresh_list()
            # Cập nhật trạng thái từng máy trên card
            for worker in self.active_workers:
                if worker.device_id in self.device_cards:
                    color = "#22D3EE" if worker.running else "#888" # Cyan for running
                    if worker.is_lagging: color = "#FB923C" # Orange for lag
                    if worker.status == "Xong": color = "#4ADE80" # Green for done
                    
                    self.device_cards[worker.device_id]["status"].configure(
                        text=worker.status, 
                        text_color=color
                    )
            # Cập nhật thông số tổng quát
            self.update_stats_ui()
        self.after(0, _update)


    def save_config(self):
        config = {"ld_path": self.ld_path_entry.get().strip()}
        with open("config.json", "w") as f:
            json.dump(config, f)
        self.add_log("HỆ THỐNG: Đã lưu đường dẫn LDPlayer.")

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

    def scan_devices(self):
        base_path = self.ld_path_entry.get().strip()
        self.adb_path = os.path.join(base_path, "adb.exe")
        if not os.path.exists(self.adb_path): self.adb_path = "adb"
        
        for w in self.device_list_frame.winfo_children(): w.destroy()
        self.device_cards = {}
        
        try:
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            lines = res.stdout.strip().split('\n')[1:]
            device_serials = [line.split('\t')[0] for line in lines if "device" in line]
            
            for i, serial in enumerate(device_serials):
                # Card siêu nhỏ gọn (Compact UI)
                card = ctk.CTkFrame(self.device_list_frame, fg_color="#252525", corner_radius=6, border_width=1, border_color="#383838")
                card.grid(row=i // 10, column=i % 10, padx=3, pady=3, sticky="nsew")
                
                # Chỉ hiển thị phần ID cuối của device cho gọn
                display_name = serial.split(":")[-1] if ":" in serial else serial
                name_lbl = ctk.CTkLabel(card, text=display_name, font=ctk.CTkFont(size=10, weight="bold"))
                name_lbl.pack(pady=(5, 0))
                
                status_lbl = ctk.CTkLabel(card, text="Sẵn sàng", font=ctk.CTkFont(size=9), text_color="#666")
                status_lbl.pack(pady=(0, 5))
                
                self.device_cards[serial] = {"card": card, "status": status_lbl}

            if not self.device_cards:
                self.add_log("CẢNH BÁO: Không tìm thấy thiết bị nào.")
            self.update_stats_ui()
        except:
            self.add_log("LỖI: Không thể quét thiết bị.")

    # Gỡ bỏ hàm select_all_devices vì không dùng checkbox nữa


    def add_item(self):
        c = self.code_input.get().strip()
        n = self.count_input.get().strip()
        if c and n.isdigit():
            self.codes_data.append({"code": c, "count": int(n)})
            self.refresh_list()
            self.code_input.delete(0, "end")
        else: self.add_log("LỖI: Mã hoặc số lượng không hợp lệ.")

    def refresh_list(self):
        def _refresh():
            for widget in self.scroll_q.winfo_children(): widget.destroy()
            for i, item in enumerate(self.codes_data):
                f = ctk.CTkFrame(self.scroll_q, fg_color="#282828", corner_radius=8)
                f.pack(fill="x", pady=3, padx=5)
                f.grid_columnconfigure(0, weight=1) # Code name expands
                
                ctk.CTkLabel(f, text=item["code"], font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=0, padx=15, pady=5, sticky="w")
                ctk.CTkLabel(f, text=f"Còn {item['count']}", text_color=ACCENT_GREEN).grid(row=0, column=1, padx=10, sticky="e")
                ctk.CTkButton(f, text="X", width=25, height=25, fg_color="#444", text_color="#AAA", hover_color=ACCENT_RED, command=lambda idx=i: self.remove_item(idx)).grid(row=0, column=2, padx=10)
        self.after(0, _refresh)

    def remove_item(self, index):
        if not self.active_workers:
            del self.codes_data[index]
            self.refresh_list()

    def add_log(self, text):
        def _log():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{timestamp}] {text}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _log)
        print(f"DEBUG: {text}")

    def start_all(self):
        # Kiểm tra Hạn dùng trước khi chạy
        if os.path.exists(LICENSE_FILE):
             with open(LICENSE_FILE, "r") as f:
                saved_key = f.read().strip()
             valid, msg = verify_license(saved_key, get_hwid())
             if not valid:
                 # Hết hạn hoặc sai mã -> Mở lại Login
                 self.destroy()
                 LoginApp().mainloop()
                 return
        else:
             self.destroy()
             LoginApp().mainloop()
             return

        selected_serials = list(self.device_cards.keys()) # Chạy tất cả máy được tìm thấy
        if not selected_serials:
            self.add_log("LỖI: Không tìm thấy thiết bị nào để chạy.")
            return
        if not self.codes_data:
            self.add_log("LỖI: Danh sách mã đang trống.")
            return

        # Removed script.json loading as script is now hardcoded in AutoClickerInstance.run
        # try:
        #     with open("script.json", "r") as f: script_data = json.load(f)
        # except:
        #     self.add_log("LỖI: Không thấy script.json")
        #     return

        self.btn_start.configure(state="disabled", text=" ĐANG CHẠY...")
        self.btn_stop.configure(state="normal", fg_color=ACCENT_RED)
        
        # Reset Stats
        self.success_count = 0
        self.failure_count = 0
        self.start_timestamp = time.time()
        self.update_stats_ui()

        # Chạy đa luồng
        self.active_workers = []
        for serial in selected_serials:
            worker = AutoClickerInstance(serial, self.adb_path, self.add_log, self.update_all_ui, self.report_stats)
            self.active_workers.append(worker)
            # Sửa lại cách truyền tham số chuẩn cho luồng chạy
            t = threading.Thread(target=worker.run, args=(self.codes_data,), daemon=True)
            t.start()

    def stop_all(self):
        for w in self.active_workers: w.running = False
        self.active_workers = []
        self.btn_start.configure(state="normal", text=" CHẠY TẤT CẢ")
        self.btn_stop.configure(state="disabled", fg_color="#333")
        self.add_log("!!! ĐANG DỪNG TẤT CẢ CÁC MÁY...")

# --- Login Screen (Activation) ---

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
        # Logo & Title
        ctk.CTkLabel(self, text="MegaUpLvCFTool(LD)", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(40, 10))
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
    # Kiểm tra Key cũ
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

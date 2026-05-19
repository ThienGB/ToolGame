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
import cv2
import numpy as np
import customtkinter as ctk
from PIL import Image
import sys
import gc
import difflib
import tkinter.filedialog as fd

# Ensure console output uses UTF-8 to avoid UnicodeEncodeError on Windows console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# Fix torch/easyocr conflicts
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass

if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    _internal = os.path.join(_meipass, '_internal')
    for dp in [_meipass, _internal, os.path.join(_internal, 'torch', 'lib'), os.path.join(_meipass, 'torch', 'lib')]:
        if os.path.exists(dp):
            if hasattr(os, 'add_dll_directory'):
                try: os.add_dll_directory(dp)
                except: pass
            os.environ['PATH'] = dp + os.pathsep + os.environ.get('PATH', '')

# --- Theme Configuration (Cyberpunk Premium Dark) ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#060A13"         # Deep Cosmic Navy/Black
NAV_COLOR = "#0C1322"        # Dark Slate Navy
CARD_COLOR = "#141D2F"       # Sleek Card Background
BORDER_COLOR = "#1D2D44"     # Thin futuristic border
ACCENT_CYAN = "#00D2FF"      # Sci-Fi Cyan
ACCENT_GREEN = "#10B981"     # Emerald Green
ACCENT_RED = "#EF4444"       # Coral Red
TEXT_MUTED = "#8B9BB4"       # Muted silver text

# License definitions
SECRET_KEY = "RyoUTE_MegaUpLvLQ_2026"
LICENSE_FILE = "license.bin"

# Lazy-loaded OCR
easyocr = None
_ocr_reader = None

def init_ocr_reader(log_func=None):
    global easyocr, _ocr_reader
    if _ocr_reader is not None:
        return _ocr_reader
    try:
        if log_func: log_func("Đang khởi tạo công cụ OCR (lần đầu sẽ mất vài giây)...")
        import easyocr as ocr_lib
        try:
            import torch
            torch.set_num_threads(1)        # Limit threads to avoid high CPU spikes
            torch.set_num_interop_threads(1) # Prevent background thread contention
        except:
            pass
        easyocr = ocr_lib
        # Explicitly load both Vietnamese and English language models
        _reader = easyocr.Reader(['vi', 'en'], gpu=False, verbose=False)
        _ocr_reader = _reader
        if log_func: log_func("Đồng bộ OCR tiếng Việt thành công! Đã sẵn sàng quét chữ.")
        return _ocr_reader
    except Exception as e:
        if log_func: log_func(f"LỖI KHÔNG NẠP ĐƯỢC BỘ OCR: {str(e)}")
        return None

# --- Helper Utilities for Answers Database ---
# Alternating line-by-line format:
# Line 1: Question
# Line 2: Answer
# Line 3: Question
# Line 4: Answer
def load_answers(file_path="dapan.txt"):
    db = {}
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("Thủ đô của Việt Nam là gì\nHà Nội\n")
                f.write("2 + 2 bằng mấy\n4\n")
        except Exception:
            pass
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f]
            valid_lines = [l for l in lines if l]
            for i in range(0, len(valid_lines) - 1, 2):
                q = valid_lines[i]
                a = valid_lines[i+1]
                db[q.lower()] = a
    except Exception as e:
        print(f"Error loading answers: {e}")
    return db

# Advanced Vietnamese accent normalizer
def strip_accents(text):
    patterns = {
        '[àáạảãâầấậẩẫăằắặẳẵ]': 'a',
        '[èéẹẻẽêềếệểễ]': 'e',
        '[ìíịỉĩ]': 'i',
        '[òóọỏõôồốộổỗơờớợởỡ]': 'o',
        '[ùúụủũưừứựửữ]': 'u',
        '[ỳýỵỷỹ]': 'y',
        '[đ]': 'd',
        '[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ]': 'A',
        '[ÈÉẸẺẼÊỀẾỆỂỄ]': 'E',
        '[ÌÍỊỈĨ]': 'I',
        '[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]': 'O',
        '[ÙÚỤỦŨƯỪỨỰỬỮ]': 'U',
        '[ÝỲỴỶỸ]': 'Y',
        '[Đ]': 'D'
    }
    for pattern, replacement in patterns.items():
        text = re.sub(pattern, replacement, text)
    return text

def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    # Keep Vietnamese letters intact during primary cleanup
    text = re.sub(r'[^a-zA-Z0-9\sàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Smart dual-level ratio calculation for maximum accuracy
def get_match_ratio(str1, str2):
    norm1 = normalize_text(str1)
    norm2 = normalize_text(str2)
    if not norm1 or not norm2:
        return 0.0
        
    # 1. Exact match with accents
    ratio_accented = difflib.SequenceMatcher(None, norm1, norm2).ratio()
    
    # 2. Unaccented matching (acts as an incredibly robust fallback if OCR misidentifies accents)
    unac_norm1 = strip_accents(norm1)
    unac_norm2 = strip_accents(norm2)
    ratio_unaccented = difflib.SequenceMatcher(None, unac_norm1, unac_norm2).ratio()
    
    # Penalize the unaccented slightly (by 0.98) so that accented is always preferred if correct
    return max(ratio_accented, ratio_unaccented * 0.98)

def find_best_match(query, database_keys, threshold=0.55):
    best_match = None
    best_ratio = 0.0
    for q in database_keys:
        ratio = get_match_ratio(query, q)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = q
    if best_ratio >= threshold:
        return best_match, best_ratio
    return None, 0.0

# --- HWID and Key system ---
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
        if winreg:
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
        if signature != expected_sig:
            return False, "Key không hợp lệ cho máy này!"
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expiry_date:
            return False, f"Key đã hết hạn vào {expiry_str}!"
        return True, expiry_str
    except:
        return False, "Key sai định dạng!"

# --- License Login Window ---
class LoginApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("KÍCH HOẠT CONFIG OCR")
        self.geometry("520x560")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        self.hwid = get_hwid()
        self.setup_ui()

    def setup_ui(self):
        ctk.CTkLabel(self, text="MegaUpLvLQTool(OCR)", font=ctk.CTkFont(size=24, weight="bold"), text_color=ACCENT_CYAN).pack(pady=(45, 10))
        ctk.CTkLabel(self, text="HỆ THỐNG XÁC THỰC BẢN QUYỀN", font=ctk.CTkFont(size=12), text_color=TEXT_MUTED).pack(pady=(0, 30))

        hwid_frame = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=12, border_width=1, border_color=BORDER_COLOR)
        hwid_frame.pack(padx=40, fill="x")
        
        ctk.CTkLabel(hwid_frame, text="MÃ MÁY CỦA BẠN (HWID):", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(12, 0))
        self.hwid_entry = ctk.CTkEntry(hwid_frame, placeholder_text=self.hwid, height=35, font=ctk.CTkFont(size=12), fg_color=BG_COLOR, border_color=BORDER_COLOR)
        self.hwid_entry.insert(0, self.hwid)
        self.hwid_entry.configure(state="readonly")
        self.hwid_entry.pack(padx=20, pady=(5, 15), fill="x")
        
        ctk.CTkLabel(self, text="Hãy gửi mã trên cho Admin để nhận Key kích hoạt.", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=5)

        self.key_input = ctk.CTkEntry(self, placeholder_text="Nhập Key kích hoạt tại đây...", height=42, fg_color=CARD_COLOR, border_color=BORDER_COLOR)
        self.key_input.pack(padx=40, pady=20, fill="x")

        self.btn_activate = ctk.CTkButton(self, text="KÍCH HOẠT NGAY", command=self.activate, height=45, corner_radius=10, font=ctk.CTkFont(weight="bold"), fg_color=ACCENT_CYAN, text_color=BG_COLOR, hover_color="#00B8E6")
        self.btn_activate.pack(padx=40, pady=5, fill="x")
        
        self.status_label = ctk.CTkLabel(self, text="", text_color=ACCENT_RED)
        self.status_label.pack(pady=10)

        ctk.CTkLabel(self, text="Nguồn: RyoUTE", font=ctk.CTkFont(size=12, weight="bold"), text_color="#3A4F72").pack(side="bottom", pady=20)

    def activate(self):
        key = self.key_input.get().strip()
        if not key:
            self.status_label.configure(text="Vui lòng nhập Key!")
            return
        valid, msg = verify_license(key, self.hwid)
        if valid:
            with open(LICENSE_FILE, "w") as f:
                f.write(key)
            self.status_label.configure(text=f"Kích hoạt thành công! Hạn dùng: {msg}", text_color=ACCENT_GREEN)
            self.after(1500, self.launch_main)
        else:
            self.status_label.configure(text=msg, text_color=ACCENT_RED)

    def launch_main(self):
        self.destroy()
        main_app = MultiPremiumApp()
        main_app.mainloop()

# --- Main OCR Answering Application ---
class MultiPremiumApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvLQTool - Trả lời Câu hỏi Tự động qua OCR")
        self.geometry("1100x700")
        self.configure(fg_color=BG_COLOR)
        
        self.adb_path = self.find_adb()
        self.devices = []
        self.is_running = False
        self.engine_thread = None
        self.answer_file_path = "dapan.txt"
        
        # Load ROI coordinates
        self.coords = {
            "question": [150, 80, 660, 80],
            "opt_a": [170, 200, 620, 50],
            "opt_b": [170, 260, 620, 50],
            "opt_c": [170, 320, 620, 50],
            "opt_d": [170, 380, 620, 50]
        }
        self.load_coords_config()

        # UI Setup
        self.setup_layout()
        self.scan_devices()
        
        # Prefetch OCR in background
        threading.Thread(target=init_ocr_reader, args=(self.add_log,), daemon=True).start()

    def find_adb(self):
        paths = ["adb", r"C:\LDPlayer\LDPlayer9\adb.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"]
        for p in paths:
            try:
                subprocess.run([p, "version"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return p
            except:
                continue
        return "adb"

    def setup_layout(self):
        # 1. Sidebar (Control center)
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=NAV_COLOR, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        
        ctk.CTkLabel(self.sidebar, text="AUTO ANSWER OCR", font=ctk.CTkFont(size=20, weight="bold"), text_color=ACCENT_CYAN).pack(pady=(30, 2))
        ctk.CTkLabel(self.sidebar, text="Premium Auto Answering Engine", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(0, 20))

        # Device Selection Card
        dev_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        dev_card.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(dev_card, text="THIẾT BỊ GIẢ LẬP", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(8, 2))
        
        self.selected_device = ctk.StringVar(value="Chưa chọn thiết bị")
        self.device_combo = ctk.CTkOptionMenu(dev_card, variable=self.selected_device, values=["Chưa chọn thiết bị"], fg_color=BG_COLOR, button_color=BORDER_COLOR, dropdown_fg_color=NAV_COLOR, height=30)
        self.device_combo.pack(padx=10, pady=5, fill="x")
        
        ctk.CTkButton(dev_card, text="Làm Mới ADB", command=self.scan_devices, height=24, font=ctk.CTkFont(size=10, weight="bold"), fg_color=BORDER_COLOR, text_color=ctk.CTkLabel(self).cget("text_color")).pack(padx=10, pady=(0, 10), fill="x")

        # Config Card
        cfg_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        cfg_card.pack(padx=15, pady=10, fill="x")
        ctk.CTkLabel(cfg_card, text="QUẢN LÝ CẤU HÌNH", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(8, 2))
        
        ctk.CTkButton(cfg_card, text="Lưu Tọa Độ", command=self.save_coords_config, height=28, fg_color=BORDER_COLOR).pack(padx=10, pady=10, fill="x")

        # Answer File Card (New custom premium file selection logic)
        ans_card = ctk.CTkFrame(self.sidebar, fg_color=CARD_COLOR, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        ans_card.pack(padx=15, pady=5, fill="x")
        ctk.CTkLabel(ans_card, text="FILE CƠ SỞ ĐÁP ÁN", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(8, 2))
        
        self.lbl_ans_path = ctk.CTkLabel(ans_card, text=os.path.basename(self.answer_file_path), font=ctk.CTkFont(size=11, weight="bold"), text_color=ACCENT_CYAN, wraplength=200)
        self.lbl_ans_path.pack(padx=10, pady=2)
        
        ctk.CTkButton(ans_card, text="Chọn File Đáp Án", command=self.choose_answer_file, height=28, fg_color=BORDER_COLOR).pack(padx=10, pady=(5, 10), fill="x")

        # Bottom Controls
        self.btn_stop = ctk.CTkButton(self.sidebar, text="DỪNG QUÉT (F2)", command=self.stop_ocr_engine, fg_color="#333", text_color="#aaa", height=40, corner_radius=10, font=ctk.CTkFont(weight="bold"), state="disabled")
        self.btn_stop.pack(side="bottom", padx=15, pady=10, fill="x")
        
        self.btn_start = ctk.CTkButton(self.sidebar, text="BẮT ĐẦU QUÉT (F1)", command=self.start_ocr_engine, fg_color=ACCENT_GREEN, text_color=BG_COLOR, hover_color="#0E9F6E", height=40, corner_radius=10, font=ctk.CTkFont(weight="bold"))
        self.btn_start.pack(side="bottom", padx=15, pady=5, fill="x")

        # Register hotkeys
        self.bind_all("<F1>", lambda event: self.start_ocr_engine())
        self.bind_all("<F2>", lambda event: self.stop_ocr_engine())

        # 2. Main Content Area
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.pack(side="right", fill="both", expand=True, padx=20, pady=20)

        # Tabview Setup (Clean 2-tab layout with standard kwargs to prevent ValueError on segmented_button_selected_text_color)
        self.tabview = ctk.CTkTabview(self.main_content, fg_color=CARD_COLOR, border_width=1, border_color=BORDER_COLOR)
        self.tabview.pack(fill="both", expand=True)
        
        self.tab_coords = self.tabview.add("Căn Chỉnh Tọa Độ (ROI)")
        self.tab_logs = self.tabview.add("Nhật Ký Quét")

        self.setup_coords_tab()
        self.setup_logs_tab()

    # --- TAB 1: Coordinates Alignment Setup ---
    def setup_coords_tab(self):
        instruction = ctk.CTkLabel(self.tab_coords, text="CẤU HÌNH CÁC KHUNG ROI TRÊN GIẢ LẬP (ĐỘ PHÂN GIẢI MẶC ĐỊNH SỬ DỤNG LÀ PIXEL)", font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_CYAN)
        instruction.pack(pady=15)

        self.roi_entries = {}
        regions_list = [
            ("question", "Vùng Câu Hỏi:"),
            ("opt_a", "Vùng Đáp Án A:"),
            ("opt_b", "Vùng Đáp Án B:"),
            ("opt_c", "Vùng Đáp Án C:"),
            ("opt_d", "Vùng Đáp Án D:")
        ]

        for reg_key, reg_name in regions_list:
            row_frame = ctk.CTkFrame(self.tab_coords, fg_color="transparent")
            row_frame.pack(fill="x", padx=40, pady=6)
            
            # Label
            lbl = ctk.CTkLabel(row_frame, text=reg_name, width=130, anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
            lbl.pack(side="left")

            # Entry inputs
            inputs_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            inputs_frame.pack(side="left", fill="x", expand=True)
            
            val = self.coords[reg_key]
            e_x = ctk.CTkEntry(inputs_frame, width=70, placeholder_text="X", fg_color=BG_COLOR, border_color=BORDER_COLOR)
            e_x.insert(0, str(val[0]))
            e_x.pack(side="left", padx=5)

            e_y = ctk.CTkEntry(inputs_frame, width=70, placeholder_text="Y", fg_color=BG_COLOR, border_color=BORDER_COLOR)
            e_y.insert(0, str(val[1]))
            e_y.pack(side="left", padx=5)

            e_w = ctk.CTkEntry(inputs_frame, width=70, placeholder_text="W", fg_color=BG_COLOR, border_color=BORDER_COLOR)
            e_w.insert(0, str(val[2]))
            e_w.pack(side="left", padx=5)

            e_h = ctk.CTkEntry(inputs_frame, width=70, placeholder_text="H", fg_color=BG_COLOR, border_color=BORDER_COLOR)
            e_h.insert(0, str(val[3]))
            e_h.pack(side="left", padx=5)

            # Store references
            self.roi_entries[reg_key] = (e_x, e_y, e_w, e_h)

            # Test preview Button
            btn_test = ctk.CTkButton(row_frame, text="XEM TRƯỚC", width=100, font=ctk.CTkFont(size=11, weight="bold"), fg_color=NAV_COLOR, border_width=1, border_color=BORDER_COLOR, command=lambda k=reg_key: self.test_roi_crop(k))
            btn_test.pack(side="right", padx=10)

        # Quick Test All Button
        btn_full_ocr_test = ctk.CTkButton(self.tab_coords, text="TEST OCR CẢ 5 KHUNG NGAY LẬP TỨC", height=38, font=ctk.CTkFont(size=12, weight="bold"), fg_color=ACCENT_CYAN, text_color=BG_COLOR, hover_color="#00B8E6", command=self.trigger_instant_ocr_test)
        btn_full_ocr_test.pack(pady=35)

    def test_roi_crop(self, key):
        device_id = self.selected_device.get()
        if not device_id or device_id == "Chưa chọn thiết bị":
            self.add_log("LỖI: Vui lòng kết nối và chọn thiết bị giả lập ở sidebar trước.")
            return
        
        try:
            ex, ey, ew, eh = self.roi_entries[key]
            x, y, w, h = int(ex.get()), int(ey.get()), int(ew.get()), int(eh.get())
        except Exception:
            self.add_log("LỖI: Định dạng tọa độ nhập vào phải là số nguyên!")
            return

        screen = self.get_screenshot(device_id)
        if screen is None:
            self.add_log("LỖI: Không thể chụp ảnh màn hình giả lập. Kiểm tra ADB.")
            return

        h_full, w_full = screen.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_full, x1 + w), min(h_full, y1 + h)

        if x2 <= x1 or y2 <= y1:
            self.add_log("LỖI: Vùng tọa độ cắt không hợp lệ!")
            return

        crop = screen[y1:y2, x1:x2]
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(crop_rgb)

        # Premium Toplevel crop visualizer
        pop = ctk.CTkToplevel(self)
        pop.title(f"Xem trước vùng cắt - {key.upper()}")
        pop.geometry(f"{max(350, w + 40)}x{max(150, h + 80)}")
        pop.configure(fg_color=BG_COLOR)
        pop.resizable(True, True)
        pop.lift()
        pop.attributes("-topmost", True)

        img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(w, h))
        lbl = ctk.CTkLabel(pop, image=img_ctk, text="")
        lbl.pack(pady=15, padx=15, expand=True)

        ctk.CTkLabel(pop, text=f"Tọa độ: X={x}, Y={y}, W={w}, H={h}", font=ctk.CTkFont(size=10), text_color=TEXT_MUTED).pack(pady=(0, 10))

    # --- TAB 2: Live Log Terminal ---
    def setup_logs_tab(self):
        log_header = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(log_header, text="NHẬT KÝ HOẠT ĐỘNG HOÀN THỜI GIAN THỰC", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(side="left")
        ctk.CTkButton(log_header, text="Xóa Log", command=self.clear_logs, width=80, height=22, font=ctk.CTkFont(size=10)).pack(side="right")

        self.log_textbox = ctk.CTkTextbox(self.tab_logs, fg_color=BG_COLOR, border_color=BORDER_COLOR, border_width=1, font=ctk.CTkFont(family="Consolas", size=12), text_color="#A8FFB2")
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_textbox.configure(state="disabled")

    def add_log(self, text):
        def _write():
            t_stamp = datetime.now().strftime("[%H:%M:%S] ")
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", f"{t_stamp}{text}\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
            print(f"OCR Log: {text}")
        self.after(0, _write)

    def clear_logs(self):
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

    # --- Choice of answer file selector ---
    def choose_answer_file(self):
        file_path = fd.askopenfilename(
            title="Chọn File Đáp Án (định dạng dòng nối dòng)",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if file_path:
            self.answer_file_path = file_path
            self.lbl_ans_path.configure(text=os.path.basename(file_path))
            self.add_log(f"HỆ THỐNG: Đã đổi file cơ sở đáp án sang: {file_path}")
            self.save_coords_config()

    # --- Coordinates Persistency Configs ---
    def save_coords_config(self):
        coords_to_save = {}
        for key, entries in self.roi_entries.items():
            try:
                coords_to_save[key] = [int(entries[0].get()), int(entries[1].get()), int(entries[2].get()), int(entries[3].get())]
            except:
                self.add_log("LỖI: Tọa độ nhập không hợp lệ, không thể lưu cấu hình config.json.")
                return
        self.coords = coords_to_save
        
        config_data = dict(self.coords)
        config_data["answer_file_path"] = self.answer_file_path
        
        try:
            with open("config.json", "w") as f:
                json.dump(config_data, f, indent=4)
            self.add_log("HỆ THỐNG: Đã lưu tọa độ và file đáp án vào file config.json.")
        except Exception as e:
            self.add_log(f"LỖI: Không thể ghi file config.json! {e}")

    def load_coords_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", "r") as f:
                    saved = json.load(f)
                if isinstance(saved, dict):
                    # Coords
                    for k in self.coords.keys():
                        if k in saved and len(saved[k]) == 4:
                            self.coords[k] = saved[k]
                    # Custom answer path
                    if "answer_file_path" in saved:
                        self.answer_file_path = saved["answer_file_path"]
            except Exception as e:
                print(f"Error loading config.json: {e}")

    def get_current_rois(self):
        rois = {}
        for key, entries in self.roi_entries.items():
            rois[key] = [int(entries[0].get()), int(entries[1].get()), int(entries[2].get()), int(entries[3].get())]
        return rois

    # --- ADB helpers ---
    def scan_devices(self):
        threading.Thread(target=self._perform_scan, daemon=True).start()

    def _perform_scan(self):
        self.add_log("Đang quét thiết bị giả lập mở cổng ADB...")
        try:
            # Try to connect default emulator ports
            for i in range(5):
                subprocess.Popen([self.adb_path, "connect", f"127.0.0.1:{5554 + i*2}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(1)
            
            res = subprocess.run([self.adb_path, "devices"], capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            lines = res.stdout.strip().split('\n')[1:]
            active_devs = [line.split('\t')[0] for line in lines if "device" in line and "offline" not in line]
            
            self.after(0, lambda: self._update_device_ui(active_devs))
        except Exception as e:
            self.add_log(f"LỖI QUÉT ADB: {e}")

    def _update_device_ui(self, active_devs):
        self.devices = active_devs
        if not active_devs:
            self.device_combo.configure(values=["Chưa chọn thiết bị"])
            self.selected_device.set("Chưa chọn thiết bị")
            self.add_log("CẢNH BÁO: Không phát hiện thấy thiết bị giả lập nào online!")
        else:
            self.device_combo.configure(values=active_devs)
            self.selected_device.set(active_devs[0])
            self.add_log(f"HỆ THỐNG: Đã phát hiện {len(active_devs)} thiết bị online. Đã chọn {active_devs[0]}")

    def call_adb(self, device_id, args):
        cmd = [self.adb_path, "-s", device_id] + args
        return subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def get_screenshot(self, device_id):
        try:
            cmd = [self.adb_path, "-s", device_id, "shell", "screencap", "-p"]
            process = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            if process.returncode != 0:
                return None
            image_bytes = process.stdout.replace(b"\r\n", b"\n")
            image_array = np.frombuffer(image_bytes, dtype=np.uint8)
            return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"Screenshot Error: {e}")
            return None

    def crop_region(self, screen, x, y, w, h):
        h_full, w_full = screen.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_full, x1 + w), min(h_full, y1 + h)
        if x2 <= x1 or y2 <= y1:
            return None
        crop = screen[y1:y2, x1:x2]
        
        # Adaptive Resize: only double size if the cropped region is very small (height < 45px)
        # Standard question boxes (~80px) and standard options (~50px) are large enough.
        # This saves HUGE CPU processing power by bypassing the 4x pixel scaling.
        if crop.shape[0] < 45:
            crop = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
            
        return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    def ocr_read_text(self, crop_gray):
        global _ocr_reader
        if crop_gray is None or _ocr_reader is None:
            return ""
        try:
            results = _ocr_reader.readtext(crop_gray, detail=0)
            if results:
                return " ".join(results).strip()
        except Exception as e:
            print(f"OCR Reader Failure: {e}")
        return ""

    # --- Single manual instant check ---
    def trigger_instant_ocr_test(self):
        device_id = self.selected_device.get()
        if not device_id or device_id == "Chưa chọn thiết bị":
            self.add_log("LỖI: Vui lòng kết nối và chọn thiết bị giả lập ở sidebar trước.")
            return
        
        self.tabview.set("Nhật Ký Quét")
        self.add_log("=== BẮT ĐẦU TEST OCR CẢ 5 KHUNG TỌA ĐỘ ===")
        
        reader = init_ocr_reader(self.add_log)
        if reader is None:
            self.add_log("LỖI: Chưa thể nạp module OCR Reader.")
            return

        screen = self.get_screenshot(device_id)
        if screen is None:
            self.add_log("LỖI: Không thể chụp màn hình thiết bị qua ADB.")
            return

        try:
            rois = self.get_current_rois()
        except:
            self.add_log("LỖI: Tọa độ nhập không hợp lệ, vui lòng kiểm tra lại các ô tọa độ.")
            return

        # Perform crops & reads
        crops = {}
        texts = {}
        for key, (x, y, w, h) in rois.items():
            crops[key] = self.crop_region(screen, x, y, w, h)
            texts[key] = self.ocr_read_text(crops[key])

        self.add_log(f"🔍 [TEST] Chữ quét Câu hỏi: \"{texts['question']}\"")
        self.add_log(f"  ├─ OCR Đáp án A: \"{texts['opt_a']}\"")
        self.add_log(f"  ├─ OCR Đáp án B: \"{texts['opt_b']}\"")
        self.add_log(f"  ├─ OCR Đáp án C: \"{texts['opt_c']}\"")
        self.add_log(f"  ├─ OCR Đáp án D: \"{texts['opt_d']}\"")

        # Fuzzy lookup test
        db = load_answers(self.answer_file_path)
        best_q, ratio = find_best_match(texts['question'], db.keys())
        
        if best_q:
            self.add_log(f"✅ KHỚP ĐÁP ÁN: \"{best_q}\" (Độ khớp mờ: {ratio*100:.1f}%)")
            correct_ans = db[best_q]
            self.add_log(f"👉 ĐÁP ÁN ĐÚNG TRONG FILE: \"{correct_ans}\"")

            options = {
                'A': (texts['opt_a'], rois['opt_a']),
                'B': (texts['opt_b'], rois['opt_b']),
                'C': (texts['opt_c'], rois['opt_c']),
                'D': (texts['opt_d'], rois['opt_d'])
            }
            
            best_opt = None
            best_opt_ratio = 0.0
            for opt_name, (opt_text, coords) in options.items():
                r = get_match_ratio(correct_ans, opt_text)
                if r > best_opt_ratio:
                    best_opt_ratio = r
                    best_opt = opt_name

            if best_opt and best_opt_ratio >= 0.4:
                _, coords = options[best_opt]
                cx = coords[0] + coords[2] // 2
                cy = coords[1] + coords[3] // 2
                self.add_log(f"🎯 XÁC ĐỊNH CLICK ĐÁP ÁN: Chọn {best_opt} (Độ khớp chữ: {best_opt_ratio*100:.1f}%)")
                self.add_log(f"👉 TỌA ĐỘ CLICK: ({cx}, {cy})")
            else:
                self.add_log("❌ THẤT BẠI: Không so khớp được đáp án đúng với 4 Option chữ OCR.")
        else:
            self.add_log("❓ KHÔNG TÌM THẤY: Câu hỏi này chưa có trong file cơ sở đáp án.")
        self.add_log("=== HOÀN TẤT THỬ NGHIỆM ===")

    # --- Background loop auto answer runner ---
    def start_ocr_engine(self):
        if self.is_running:
            return
        
        device_id = self.selected_device.get()
        if not device_id or device_id == "Chưa chọn thiết bị":
            self.add_log("LỖI: Vui lòng kết nối và chọn thiết bị giả lập ở sidebar trước.")
            return

        self.is_running = True
        self.btn_start.configure(state="disabled", text="ĐANG QUẾT AUTO...")
        self.btn_stop.configure(state="normal", fg_color=ACCENT_RED)
        
        self.tabview.set("Nhật Ký Quét")
        self.add_log("🚀 BẮT ĐẦU CHẠY AUTOMATION LẮNG NGHE OCR CÂU HỎI...")

        self.engine_thread = threading.Thread(target=self.engine_loop, daemon=True)
        self.engine_thread.start()

    def stop_ocr_engine(self):
        if not self.is_running:
            return
        self.is_running = False
        self.btn_start.configure(state="normal", text="BẮT ĐẦU QUÉT (F1)")
        self.btn_stop.configure(state="disabled", fg_color="#333")
        self.add_log("🛑 ĐÃ DỪNG AUTOMATION LẮNG NGHE OCR.")

    def engine_loop(self):
        # Hot reload reader
        reader = init_ocr_reader(self.add_log)
        if reader is None:
            self.add_log("LỖI: Không thể tải mô hình OCR, dừng automation.")
            self.after(0, self.stop_ocr_engine)
            return

        last_processed_question = ""
        
        while self.is_running:
            device_id = self.selected_device.get()
            if not device_id or device_id == "Chưa chọn thiết bị":
                time.sleep(2)
                continue

            screen = self.get_screenshot(device_id)
            if screen is None:
                time.sleep(1.5)
                continue

            try:
                rois = self.get_current_rois()
            except:
                self.add_log("LỖI: Sai định dạng tọa độ. Vui lòng sửa lại.")
                time.sleep(3)
                continue

            # Read Question ROI
            xq, yq, wq, hq = rois['question']
            crop_q = self.crop_region(screen, xq, yq, wq, hq)
            q_text = self.ocr_read_text(crop_q)

            if not q_text or len(q_text) < 4:
                # No question detected yet. Sleep to avoid hammering the CPU.
                time.sleep(1.5)
                continue

            # Check if this is a newly detected question
            norm_new = normalize_text(q_text)
            norm_old = normalize_text(last_processed_question)
            
            # Use fuzzy ratio to check if it's the exact same active question
            if norm_new == norm_old or (norm_old and difflib.SequenceMatcher(None, norm_new, norm_old).ratio() > 0.85):
                # Still showing the same question, avoid double clicks. Sleep longer.
                time.sleep(1.8)
                continue

            self.add_log(f"🔍 PHÁT HIỆN CÂU HỎI MỚI: \"{q_text}\"")
            last_processed_question = q_text

            db = load_answers(self.answer_file_path)
            best_q, ratio = find_best_match(q_text, db.keys())

            if best_q and ratio >= 0.6:
                correct_ans = db[best_q]
                self.add_log(f"✅ KHỚP CƠ SỞ DỮ LIỆU: \"{best_q}\" ({ratio*100:.1f}%)")
                self.add_log(f"💡 ĐÁP ÁN ĐÚNG TRONG FILE: \"{correct_ans}\"")

                # Read 4 options
                crops = {}
                texts = {}
                for key in ['opt_a', 'opt_b', 'opt_c', 'opt_d']:
                    x, y, w, h = rois[key]
                    crops[key] = self.crop_region(screen, x, y, w, h)
                    texts[key] = self.ocr_read_text(crops[key])

                self.add_log(f"  ├─ Option A OCR: \"{texts['opt_a']}\"")
                self.add_log(f"  ├─ Option B OCR: \"{texts['opt_b']}\"")
                self.add_log(f"  ├─ Option C OCR: \"{texts['opt_c']}\"")
                self.add_log(f"  ├─ Option D OCR: \"{texts['opt_d']}\"")

                options = {
                    'A': (texts['opt_a'], rois['opt_a']),
                    'B': (texts['opt_b'], rois['opt_b']),
                    'C': (texts['opt_c'], rois['opt_c']),
                    'D': (texts['opt_d'], rois['opt_d'])
                }

                best_opt = None
                best_opt_ratio = 0.0
                for opt_name, (opt_text, coords) in options.items():
                    r = get_match_ratio(correct_ans, opt_text)
                    if r > best_opt_ratio:
                        best_opt_ratio = r
                        best_opt = opt_name

                if best_opt and best_opt_ratio >= 0.4:
                    _, coords = options[best_opt]
                    cx = coords[0] + coords[2] // 2
                    cy = coords[1] + coords[3] // 2
                    self.add_log(f"🎯 XÁC ĐỊNH CHỌN: {best_opt} ({best_opt_ratio*100:.1f}%)")
                    
                    # Tap center
                    self.call_adb(device_id, ["shell", "input", "tap", str(cx), str(cy)])
                    self.add_log(f"👉 CLICK THÀNH CÔNG: ({cx}, {cy}) ✓")
                else:
                    self.add_log("❌ LỖI: Không khớp được đáp án đúng với 4 Option chữ OCR trên màn hình.")
            else:
                self.add_log(f"❓ THẤT BẠI: Không có câu hỏi nào khớp trong cơ sở đáp án (Khớp tốt nhất: {ratio*100:.1f}%)")

            time.sleep(2)
            gc.collect()

        self.after(0, self.stop_ocr_engine)


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

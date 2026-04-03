import customtkinter as ctk
import hashlib
import base64
from datetime import datetime, timedelta
import pyperclip # Thư viện để copy nhanh vào clipboard

# PHẢI TRÙNG VỚI SECRET_KEY TRONG gui_tool.py
SECRET_KEY = "RyoUTE_MegaUpLvCF_2026"

# --- Theme Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BG_COLOR = "#121212"
CARD_COLOR = "#1D1D1D"
ACCENT_GREEN = "#00D2FF"
ACCENT_PURPLE = "#A855F7"

class KeyGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MegaUpLvCFTool - KEY GENERATOR PRO")
        self.geometry("650x750")
        self.resizable(False, False)
        self.configure(fg_color=BG_COLOR)
        
        self.setup_ui()

    def setup_ui(self):
        # Header
        ctk.CTkLabel(self, text="KEY GENERATOR ADMIN", font=ctk.CTkFont(size=26, weight="bold"), text_color=ACCENT_PURPLE).pack(pady=(40, 10))
        ctk.CTkLabel(self, text="HỆ THỐNG TẠO MÃ KÍCH HOẠT BẢN QUYỀN", font=ctk.CTkFont(size=12)).pack(pady=(0, 30))

        # Main Card
        self.card = ctk.CTkFrame(self, fg_color=CARD_COLOR, corner_radius=15, border_width=1, border_color="#333")
        self.card.pack(padx=50, fill="both", expand=True, pady=(0, 40))

        # HWID Input
        ctk.CTkLabel(self.card, text="NHẬP HWID CỦA KHÁCH:", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=(20, 5))
        self.hwid_input = ctk.CTkEntry(self.card, placeholder_text="Ví dụ: 4C4C4544-004D-...", height=40, font=ctk.CTkFont(size=12))
        self.hwid_input.pack(padx=30, pady=5, fill="x")

        # Duration Frame
        dur_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        dur_frame.pack(padx=30, pady=5, fill="x")
        dur_frame.columnconfigure((0, 1, 2, 3), weight=1)

        def create_dur_box(parent, title, default, col):
            ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=col, pady=(10, 2))
            entry = ctk.CTkEntry(parent, height=35)
            entry.grid(row=1, column=col, padx=5, sticky="nsew")
            entry.insert(0, default)
            return entry

        self.days_input = create_dur_box(dur_frame, "NGÀY:", "30", 0)
        self.hours_input = create_dur_box(dur_frame, "GIỜ:", "0", 1)
        self.mins_input = create_dur_box(dur_frame, "PHÚT:", "0", 2)
        self.secs_input = create_dur_box(dur_frame, "GIÂY:", "0", 3)

        # Generate Button
        self.btn_gen = ctk.CTkButton(self.card, text="TẠO KEY KÍCH HOẠT", command=self.generate, height=45, fg_color=ACCENT_GREEN, font=ctk.CTkFont(weight="bold"))
        self.btn_gen.pack(padx=30, pady=25, fill="x")

        # Result Area
        ctk.CTkLabel(self.card, text="KẾT QUẢ (DÙNG ĐỂ GỬI KHÁCH):", font=ctk.CTkFont(size=14, weight="bold"), text_color=ACCENT_GREEN).pack(pady=(30, 10))
        self.result_box = ctk.CTkTextbox(self.card, height=200, fg_color="#000", font=("Consolas", 15), border_width=2, border_color="#555")
        self.result_box.pack(padx=30, pady=10, fill="x")

        self.btn_copy = ctk.CTkButton(self.card, text="📋 SAO CHÉP KEY KÍCH HOẠT", command=self.copy_key, height=45, fg_color="#333", hover_color=ACCENT_PURPLE, font=ctk.CTkFont(weight="bold"))
        self.btn_copy.pack(padx=30, pady=15, fill="x")

    def generate(self):
        hwid = self.hwid_input.get().strip()
        
        try:
            d = int(self.days_input.get().strip() or 0)
            h = int(self.hours_input.get().strip() or 0)
            m = int(self.mins_input.get().strip() or 0)
            s = int(self.secs_input.get().strip() or 0)
        except ValueError:
            self.show_error("Thời gian phải là số nguyên!")
            return
        
        if not hwid:
            self.show_error("Vui lòng nhập HWID!")
            return

        # Tính toán thời gian hết hạn chính xác đến từng giây
        expiry = (datetime.now() + timedelta(days=d, hours=h, minutes=m, seconds=s)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Tạo signature tương tự như gui_tool.py
        sig = hashlib.sha256(f"{expiry}{hwid}{SECRET_KEY}".encode()).hexdigest()[:10]
        full_key = base64.b64encode(f"{expiry}|{sig}".encode()).decode()
        
        self.result_box.configure(state="normal") # Mở để ghi
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", full_key)
        self.result_box.configure(state="disabled") # Khóa để chỉ xem
        
        self.btn_gen.configure(text="TẠO KEY MỚI THÀNH CÔNG!", fg_color="#4ADE80")
        self.after(2000, lambda: self.btn_gen.configure(text="TẠO KEY KÍCH HOẠT", fg_color=ACCENT_GREEN))

    def copy_key(self):
        key = self.result_box.get("1.0", "end-1c").strip()
        if key:
            try:
                pyperclip.copy(key)
                self.btn_copy.configure(text="ĐÃ SAO CHÉP!", fg_color="#4ADE80")
                self.after(1500, lambda: self.btn_copy.configure(text="SAO CHÉP KEY", fg_color="#333"))
            except:
                pass # Có thể chưa cài pyperclip

    def show_error(self, msg):
        self.result_box.configure(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("1.0", f"LỖI: {msg}")
        self.result_box.configure(state="disabled")

if __name__ == "__main__":
    app = KeyGeneratorApp()
    app.mainloop()

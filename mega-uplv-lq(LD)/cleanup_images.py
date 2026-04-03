import os

files_to_delete = [
    "images/10_win_x2_exp.png",
    "images/5v5.png",
    "images/back.png",
    "images/back1.png",
    "images/chuatungchoi.png",
    "images/co.png",
    "images/khong.png",
    "images/logo2.png",
    "images/mua.png",
    "images/mở.png",
    "images/ok1.png",
    "images/qua_nguoi_moi_button.png",
    "images/quay_lai_su_kien_button.png",
    "images/quay_lai_trang_chu_button.png",
    "images/random.png",
    "images/ratquenthuoc.png",
    "images/ruby.png",
    "images/sansang.png",
    "images/setting.png",
    "images/shopruby1.png",
    "images/start.png",
    "images/start1.png",
    "images/start2.png",
    "images/sudung.png",
    "images/sukien1.png",
    "images/sukien2.png",
    "images/sukien3.png",
    "images/sukientanthu.png",
    "images/sảnh.png",
    "images/tuido.png",
    "images/tuong.png",
    "images/vatpham.png",
    "images/vatpham1.png",
    "images/x.png",
    "images/x2.png",
    "images/x2exp.png",
    "images/x2exp1.png",
    "images/xemidphong.png",
    "debug_emulator-5554.png",
    "debug_look.png"
]

for f in files_to_delete:
    if os.path.exists(f):
        try:
            os.remove(f)
            print(f"Deleted: {f}")
        except Exception as e:
            print(f"Error deleting {f}: {e}")
    else:
        print(f"Not found: {f}")

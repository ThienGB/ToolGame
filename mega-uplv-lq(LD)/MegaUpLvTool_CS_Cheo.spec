# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# Danh sách các package cần thu thập cho OCR
pkgs = ['easyocr', 'torch', 'torchvision', 'scipy', 'numpy', 'customtkinter', 'cv2']
# Lưu ý: Thay đổi logo_cs_cheo.png nếu tên file thực tế khác
datas = [
    ('images', 'images'), 
    ('logo_cs_cheo.png', '.'), 
    ('start.png', '.'), 
    ('stop.png', '.'), 
    ('adb.exe', '.'), 
    ('AdbWinApi.dll', '.'), 
    ('AdbWinUsbApi.dll', '.')
]
binaries = []
hiddenimports = []

for pkg in pkgs:
    t_datas, t_binaries, t_hiddenimports = collect_all(pkg)
    datas += t_datas
    binaries += t_binaries
    hiddenimports += t_hiddenimports

# Tối ưu hóa: Loại bỏ các module không cần thiết để build nhanh hơn
excluded_modules = [
    'matplotlib', 'pandas', 'IPython', 'jedi', 'notebook', 
    'docutils', 'PIL.ImageQt', 'tkinter.test',
    'torch.distributions', 'torch.testing', 'torch.utils.benchmark'
]

a = Analysis(
    ['gui_tool_cs_cheo.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MegaUpLvTool_CS_Cheo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MegaUpLvTool_CS_Cheo',
)

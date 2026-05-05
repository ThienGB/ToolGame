# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('images', 'images'), ('logo.png', '.'), ('start.png', '.'), ('stop.png', '.')]
binaries = []
hiddenimports = []

# Thu thập đầy đủ các thư viện nặng và hay lỗi
for pkg in ['easyocr', 'torch', 'torchvision', 'scipy', 'numpy', 'customtkinter', 'cv2']:
    t_datas, t_binaries, t_hiddenimports = collect_all(pkg)
    datas += t_datas
    binaries += t_binaries
    hiddenimports += t_hiddenimports

a = Analysis(
    ['gui_tool.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MegaUpLvTool',
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
    name='MegaUpLvTool',
)

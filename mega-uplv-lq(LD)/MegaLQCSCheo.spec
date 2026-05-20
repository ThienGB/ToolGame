# -*- mode: python ; coding: utf-8 -*-


# Tự động quét và thêm thư mục Tcl/Tk để tránh lỗi 'Tcl data directory not found' trên máy khách
import os
import sys
datas_list = [('images', 'images'), ('logo_cs_cheo.png', '.'), ('start.png', '.'), ('stop.png', '.')]
tcl_root = os.path.join(sys.base_prefix, 'tcl')
if os.path.exists(tcl_root):
    for f in os.listdir(tcl_root):
        f_path = os.path.join(tcl_root, f)
        if os.path.isdir(f_path):
            if f.startswith('tcl') or f.startswith('tk'):
                datas_list.append((f_path, os.path.join('_tcl_data', f)))

a = Analysis(
    ['gui_tool_cs_cheo.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='MegaLQCSCheo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

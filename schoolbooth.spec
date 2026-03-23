# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import importlib.util
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = Path(SPECPATH).resolve()
datas = [
    ('config.json', '.'),
    ('overlays.json', '.'),
    ('app.ico', '.'),
    ('app.png', '.'),
    ('LICENSE.TXT', '.'),
]

datas += collect_data_files('qt_material_icons')

watermarks_dir = project_dir / 'watermarks'
if watermarks_dir.exists():
    for watermark_file in watermarks_dir.iterdir():
        if watermark_file.is_file():
            datas.append((str(watermark_file), 'watermarks'))

escpos_spec = importlib.util.find_spec('escpos')
if escpos_spec and escpos_spec.origin:
    escpos_capabilities = Path(escpos_spec.origin).resolve().parent / 'capabilities.json'
    if escpos_capabilities.exists():
        datas.append((str(escpos_capabilities), 'escpos'))


a = Analysis(
    ['schoolbooth.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=['escpos', 'escpos.printer', 'win32print', 'win32api', 'win32con', 'win32gui', 'PyQt5.QtSvg', 'qtpy.QtSvg'] + collect_submodules('qt_material_icons'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['grp', 'pwd', 'readline'],
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
    name='schoolbooth',
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
    icon=['app.ico'],
)

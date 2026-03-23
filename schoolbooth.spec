# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import importlib.util
from PyInstaller.utils.hooks import collect_submodules

project_dir = Path(SPECPATH).resolve()
datas = [
    ('config.json', '.'),
    ('overlays.json', '.'),
    ('app.ico', '.'),
    ('app.png', '.'),
    ('LICENSE.TXT', '.'),
]

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
    hiddenimports=[
        'escpos', 'escpos.printer',
        'win32print', 'win32api', 'win32con', 'win32gui',
        'PyQt5.QtSvg', 'qtpy.QtSvg',
        # qt_material_icons resource modules live in a directory without __init__.py
        # so collect_submodules() misses them — list them explicitly.
        'qt_material_icons.resources.icons_outlined_20',
        'qt_material_icons.resources.icons_outlined_24',
        'qt_material_icons.resources.icons_outlined_40',
        'qt_material_icons.resources.icons_outlined_48',
        'qt_material_icons.resources.icons_rounded_20',
        'qt_material_icons.resources.icons_rounded_24',
        'qt_material_icons.resources.icons_rounded_40',
        'qt_material_icons.resources.icons_rounded_48',
        'qt_material_icons.resources.icons_sharp_20',
        'qt_material_icons.resources.icons_sharp_24',
        'qt_material_icons.resources.icons_sharp_40',
        'qt_material_icons.resources.icons_sharp_48',
    ] + collect_submodules('qt_material_icons'),
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

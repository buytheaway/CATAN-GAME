# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None
# PyInstaller defines SPECPATH = directory containing the spec file
ROOT = Path(SPECPATH).resolve().parents[1]  # <repo>/tools/build -> parents[1] == <repo>
ENTRY = Path(SPECPATH) / "entry_client.py"

datas = []
binaries = []
hiddenimports = []

for pkg in ("PySide6", "shiboken6"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += [(str(ROOT / "app" / "assets"), "app/assets")]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CatanClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CatanClient",
)

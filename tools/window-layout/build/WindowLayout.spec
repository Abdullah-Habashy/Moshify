# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: one windowed WindowLayout.exe, no console, own icon."""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
UI = os.path.join(ROOT, "winlayout", "ui")
ASSETS = ("index.html", "app.js", "style.css", "icon.svg", "icon.ico")

a = Analysis(
    [os.path.join(ROOT, "WindowLayout.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(UI, name), "winlayout/ui") for name in ASSETS],
    # The backend is picked at runtime, so name it explicitly.
    hiddenimports=["winlayout.backend.win_backend"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "test", "pydoc_data", "lib2to3"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WindowLayout",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # a window, not a console; CLI runs attach to the caller's
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(UI, "icon.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
)

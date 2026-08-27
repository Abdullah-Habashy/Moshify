# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe -- two single-file executables from the same code:

* WindowLayout.exe   windowed: double-click it, or let a shortcut fire a
                     restore without a console flashing up.
* winlayout-cli.exe  console: proper stdout and a real exit code, which a
                     windowed exe cannot give a script.
"""
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
UI = os.path.join(ROOT, "winlayout", "ui")
ASSETS = ("index.html", "app.js", "style.css", "icon.svg", "icon.ico")

def analyze(script):
    return Analysis(
        [os.path.join(ROOT, script)],
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


def package(analysis, name, console):
    return EXE(
        PYZ(analysis.pure),
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=console,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=os.path.join(UI, "icon.ico"),
        version=os.path.join(SPECPATH, "version_info.txt"),
    )


app = package(analyze("WindowLayout.py"), "WindowLayout", console=False)
cli = package(analyze("winlayout-cli.py"), "winlayout-cli", console=True)

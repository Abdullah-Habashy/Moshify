"""Desktop shortcuts: the actual "one click" part of the app.

A shortcut runs the app with ``restore <layout>`` and nothing else, so it can
be double clicked or pinned to the taskbar. Packaged as an .exe that is the
exe itself; from source it is ``pythonw.exe winlayout-cli.py``.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

from . import diag
from .model import slugify


class Command(NamedTuple):
    target: str
    arguments: str
    icon: str
    workdir: str


def pythonw() -> str:
    """The windowed interpreter next to the current one, if there is one."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"


def desktop_from_known_folder() -> Optional[Path]:
    """Ask Windows where the desktop actually is.

    Guessing %USERPROFILE%\\Desktop is wrong the moment OneDrive backs the
    desktop up: the old folder can still exist, empty, while everything the
    user sees lives under OneDrive. Only the shell knows.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                        ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

        shell32 = ctypes.WinDLL("shell32")
        ole32 = ctypes.WinDLL("ole32")
        guid = GUID()
        if ole32.CLSIDFromString(FOLDERID_DESKTOP, ctypes.byref(guid)) != 0:
            return None
        pointer = ctypes.c_wchar_p()
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p)]
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None,
                                        ctypes.byref(pointer)) != 0:
            return None
        try:
            path = Path(pointer.value) if pointer.value else None
        finally:
            ole32.CoTaskMemFree(pointer)
        return path if path and path.is_dir() else None
    except Exception:
        return None


def desktop_from_registry() -> Optional[Path]:
    """User Shell Folders holds the same redirection, without any COM."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        with key:
            value, _kind = winreg.QueryValueEx(key, "Desktop")
        path = Path(os.path.expandvars(value))
        return path if path.is_dir() else None
    except Exception:
        return None


def desktop_by_guessing(profile: Optional[str] = None) -> Path:
    """Last resort. OneDrive first: when it is there, it is the real one."""
    base = Path(profile or os.environ.get("USERPROFILE") or Path.home())
    for name in ("OneDrive/Desktop", "OneDrive - Personal/Desktop",
                 "Desktop", "سطح المكتب"):
        candidate = base / name
        if candidate.is_dir():
            return candidate
    return base


def desktop_dir() -> Path:
    for finder in (desktop_from_known_folder, desktop_from_registry):
        found = finder()
        if found is not None:
            return found
    return desktop_by_guessing()


ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(name: str) -> str:
    """Keep the layout's name readable on the desktop -- spaces and all."""
    cleaned = ILLEGAL.sub("", name).strip().rstrip(".")
    return cleaned[:80] or slugify(name)


def _fallback_icon() -> str:
    system_root = os.environ.get("SystemRoot") or "C:\\Windows"
    return os.path.join(system_root, "System32", "imageres.dll") + ",110"


def shortcut_command(layout_name: str, frozen: Optional[bool] = None,
                     executable: Optional[str] = None,
                     root: Optional[Path] = None) -> Command:
    """What a shortcut for ``layout_name`` should run. Pure, so it is testable
    off Windows."""
    frozen = is_frozen() if frozen is None else frozen
    root = Path(root) if root is not None else package_root()
    if frozen:
        exe = executable or sys.executable
        return Command(exe, f'restore "{layout_name}"', f"{exe},0", str(root))
    launcher = root / "WindowLayout.pyw"
    icon = root / "winlayout" / "ui" / "icon.ico"
    return Command(
        executable or pythonw(),
        f'"{launcher}" restore "{layout_name}"',
        str(icon) if icon.exists() else _fallback_icon(),
        str(root),
    )


def _ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcut(layout_name: str, directory: Optional[Path] = None) -> Path:
    """Write ``<layout>.lnk`` on the desktop. Falls back to a .cmd file when
    PowerShell is unavailable."""
    directory = Path(directory) if directory else desktop_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{safe_filename(layout_name)}.lnk"
    command = shortcut_command(layout_name)
    diag.log(f"shortcut -> {target}")

    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut({path});"
        "$s.TargetPath = {exe};"
        "$s.Arguments = {args};"
        "$s.WorkingDirectory = {cwd};"
        "$s.IconLocation = {icon};"
        "$s.Description = {desc};"
        "$s.Save()"
    ).format(
        path=_ps_quote(target),
        exe=_ps_quote(command.target),
        args=_ps_quote(command.arguments),
        cwd=_ps_quote(command.workdir),
        icon=_ps_quote(command.icon),
        desc=_ps_quote(f"WindowLayout — {layout_name}"),
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and target.exists():
            return target
        diag.log(f"powershell could not write the .lnk: {result.stderr.strip()[:300]}")
    except (OSError, subprocess.SubprocessError):
        diag.log_exception("powershell failed while writing the shortcut")
    return _create_cmd(layout_name, directory, command)


def _create_cmd(layout_name: str, directory: Path, command: Command) -> Path:
    """Fallback when PowerShell is unavailable.

    cmd.exe reads a batch file in the console code page, so an Arabic layout
    name only survives if the file switches to UTF-8 first and carries no BOM
    (the BOM itself would be executed as a command).
    """
    target = directory / f"{safe_filename(layout_name)}.cmd"
    target.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        f'start "" "{command.target}" {command.arguments}\r\n',
        encoding="utf-8",
    )
    diag.log(f"shortcut fell back to a .cmd: {target}")
    return target


def reveal(path: Path) -> None:
    """Open Explorer with the file selected, so it is never 'where is it?'."""
    if sys.platform != "win32":
        return
    try:
        subprocess.Popen(["explorer.exe", "/select,", str(path)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        diag.log_exception("could not open Explorer on the shortcut")

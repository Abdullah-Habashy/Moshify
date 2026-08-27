"""Desktop shortcuts: the actual "one click" part of the app.

A shortcut runs the app with ``restore <layout>`` and nothing else, so it can
be double clicked or pinned to the taskbar. Packaged as an .exe that is the
exe itself; from source it is ``pythonw.exe winlayout-cli.py``.
"""
from __future__ import annotations

import ctypes
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
    icon_path: str
    icon_index: int
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


def _fallback_icon() -> tuple:
    system_root = os.environ.get("SystemRoot") or "C:\\Windows"
    return os.path.join(system_root, "System32", "imageres.dll"), 110


def shortcut_command(layout_name: str, frozen: Optional[bool] = None,
                     executable: Optional[str] = None,
                     root: Optional[Path] = None) -> Command:
    """What a shortcut for ``layout_name`` should run. Pure, so it is testable
    off Windows."""
    frozen = is_frozen() if frozen is None else frozen
    root = Path(root) if root is not None else package_root()
    if frozen:
        exe = executable or sys.executable
        return Command(exe, f'restore "{layout_name}"', exe, 0, str(root))
    launcher = root / "WindowLayout.pyw"
    icon = root / "winlayout" / "ui" / "icon.ico"
    icon_path, icon_index = ((str(icon), 0) if icon.exists() else _fallback_icon())
    return Command(
        executable or pythonw(),
        f'"{launcher}" restore "{layout_name}"',
        icon_path, icon_index,
        str(root),
    )




# COM plumbing for IShellLink. WScript.Shell -- the one line of PowerShell
# everybody uses for this -- converts the shortcut path to the system's ANSI
# code page before saving, so on a machine whose "language for non-Unicode
# programs" is not Arabic, an Arabic layout name becomes "??? ?????.lnk" and
# the save fails outright. IShellLink and IPersistFile take wide strings the
# whole way, and calling them here also drops a one-to-two second PowerShell
# start-up from every shortcut.
CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
IID_ISHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
IID_IPERSIST_FILE = "{0000010B-0000-0000-C000-000000000046}"
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 0x2

# Vtable slots, counting the three IUnknown entries first.
IUNKNOWN_QUERY_INTERFACE = 0
IUNKNOWN_RELEASE = 2
ISL_SET_DESCRIPTION = 7
ISL_SET_WORKING_DIRECTORY = 9
ISL_SET_ARGUMENTS = 11
ISL_SET_ICON_LOCATION = 17
ISL_SET_PATH = 20
IPF_SAVE = 6


class GUID(ctypes.Structure):
    """Defined here rather than inside a function so it can be an argtype:
    passing byref() against an explicit POINTER(GUID) is unambiguous, while
    passing it against a bare c_void_p relies on ctypes' conversion rules."""

    # Fixed widths, not c_ulong/c_ushort: c_ulong is 8 bytes on 64-bit Linux
    # and 4 on Windows, and a GUID has to be exactly 16 bytes.
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


def _guid(text: str) -> GUID:
    value = GUID()
    ole32 = ctypes.WinDLL("ole32")
    ole32.CLSIDFromString.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(GUID)]
    ole32.CLSIDFromString.restype = ctypes.c_long
    if ole32.CLSIDFromString(text, ctypes.byref(value)) != 0:
        raise OSError(f"bad guid {text}")
    return value


def _com_call(pointer, slot, argtypes, *args):
    """Invoke one vtable entry. HRESULT as the restype makes ctypes raise on
    a failing call, so every step is checked."""
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    return prototype(vtable[slot])(pointer, *args)


def _release(pointer) -> None:
    vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
        vtable[IUNKNOWN_RELEASE])(pointer)


def write_shell_link(path: Path, command: Command) -> Optional[str]:
    """Create the .lnk. Returns an error message, or None on success."""
    if sys.platform != "win32":
        return "الاختصارات على ويندوز بس"

    ole32 = ctypes.WinDLL("ole32")
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.HRESULT

    started = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    ours = started in (0, 1)  # S_OK / S_FALSE: only then is the balance ours
    link = ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(
            ctypes.byref(_guid(CLSID_SHELL_LINK)), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(_guid(IID_ISHELL_LINK_W)), ctypes.byref(link))
    except OSError as exc:
        if ours:
            ole32.CoUninitialize()
        return f"مانفعش نجهّز الاختصار: {exc}"

    text = [ctypes.c_wchar_p]
    try:
        _com_call(link, ISL_SET_PATH, text, command.target)
        if command.arguments:
            _com_call(link, ISL_SET_ARGUMENTS, text, command.arguments)
        if command.workdir:
            _com_call(link, ISL_SET_WORKING_DIRECTORY, text, command.workdir)
        _com_call(link, ISL_SET_DESCRIPTION, text, f"WindowLayout — {path.stem}")
        if command.icon_path:
            _com_call(link, ISL_SET_ICON_LOCATION,
                      [ctypes.c_wchar_p, ctypes.c_int],
                      command.icon_path, int(command.icon_index))

        persist = ctypes.c_void_p()
        _com_call(link, IUNKNOWN_QUERY_INTERFACE,
                  [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                  ctypes.byref(_guid(IID_IPERSIST_FILE)), ctypes.byref(persist))
        try:
            _com_call(persist, IPF_SAVE, [ctypes.c_wchar_p, ctypes.c_int],
                      str(path), 1)
        finally:
            _release(persist)
    except OSError as exc:
        return f"مانفعش نحفظ الاختصار: {exc}"
    finally:
        _release(link)
        if ours:
            ole32.CoUninitialize()

    return None if path.exists() else "الاختصار مااتكتبش"


def create_shortcut(layout_name: str, directory: Optional[Path] = None) -> Path:
    """Write ``<layout>.lnk`` on the desktop. Falls back to a .cmd file only
    if the shell refuses to make a link at all."""
    directory = Path(directory) if directory else desktop_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{safe_filename(layout_name)}.lnk"
    command = shortcut_command(layout_name)
    diag.log(f"shortcut -> {target}")

    error = write_shell_link(target, command)
    if error is None:
        return target
    diag.log(f"shell link failed: {error}")
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

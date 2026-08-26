"""Windows implementation, built on ctypes so nothing has to be pip installed.

Coordinate notes (the two traps in this API):

* Everything here is *screen* coordinates. ``WINDOWPLACEMENT`` speaks
  "workspace" coordinates instead, which differ from screen coordinates by
  the primary monitor's work-area origin -- non zero only when the taskbar
  sits at the top or the left. ``_to_workspace``/``_from_workspace`` convert.
* The process is made per-monitor DPI aware v2 before anything else, so
  ``GetWindowRect`` and ``SetWindowPos`` both speak real physical pixels on
  every monitor, whatever its scaling factor.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from typing import Optional

from ..model import (MonitorInfo, Rect, STATE_MAXIMIZED, STATE_MINIMIZED,
                     STATE_NORMAL, WindowInfo)

if sys.platform != "win32":  # pragma: no cover - import guard
    raise ImportError("winlayout.backend.win_backend requires Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    dwmapi = ctypes.WinDLL("dwmapi")
except OSError:  # pragma: no cover - ancient Windows
    dwmapi = None
try:
    shcore = ctypes.WinDLL("shcore")
except OSError:  # pragma: no cover - Windows 8 and older
    shcore = None

# --- constants ---------------------------------------------------------------
GW_OWNER = 4
GA_ROOT = 2
GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_SHOWNOACTIVATE = 4
SW_MAXIMIZE = 3
SW_SHOWMINNOACTIVE = 7
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_ASYNCWINDOWPOS = 0x4000

HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1

DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ACCESS_DENIED = 5

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# Shell surfaces that are windows but never part of a user's layout.
SKIP_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ForegroundStaging", "MultitaskingViewFrame",
    "XamlExplorerHostIslandWindow", "Windows.Internal.Shell.TabProxyWindow",
    "TaskListThumbnailWnd", "EdgeUiInputTopWndClass", "NarratorHelperWindow",
}
SKIP_TITLES = {"Program Manager", "Windows Input Experience", "Windows Shell Experience Host"}


# --- structures --------------------------------------------------------------
class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

# --- prototypes --------------------------------------------------------------
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
user32.GetWindowPlacement.restype = wintypes.BOOL
user32.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
user32.SetWindowPlacement.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.restype = wintypes.BOOL
user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                       MONITORENUMPROC, wintypes.LPARAM]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HANDLE
user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
user32.MonitorFromRect.restype = wintypes.HANDLE
user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL

_get_window_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
_get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
_get_window_long.restype = ctypes.c_ssize_t

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

_get_aumid = getattr(kernel32, "GetApplicationUserModelId", None)
if _get_aumid is not None:
    _get_aumid.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_uint32), wintypes.LPWSTR]
    _get_aumid.restype = wintypes.LONG

if dwmapi is not None:
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def enable_dpi_awareness() -> None:
    """Must run before any window is created by this process."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        if shcore is not None:
            shcore.SetProcessDpiAwareness(2)
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


# --- small helpers -----------------------------------------------------------
def _rect(win_rect: wintypes.RECT) -> Rect:
    return Rect(int(win_rect.left), int(win_rect.top),
                int(win_rect.right), int(win_rect.bottom))


def _text(getter, hwnd, size: int = 512) -> str:
    buf = ctypes.create_unicode_buffer(size)
    getter(hwnd, buf, size)
    return buf.value


def _is_cloaked(hwnd: int) -> bool:
    """Cloaked windows are hidden by the shell: other virtual desktops,
    suspended store apps, the invisible UWP frame proxies."""
    if dwmapi is None:
        return False
    value = ctypes.c_int(0)
    try:
        if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED,
                                        ctypes.byref(value), ctypes.sizeof(value)) != 0:
            return False
    except Exception:
        return False
    return value.value != 0


def _process_path(pid: int) -> tuple[Optional[str], Optional[str]]:
    """(executable path, AppUserModelId) for a pid, best effort."""
    if not pid:
        return None, None
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None, None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        path = buf.value if kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size)) else None
        aumid = None
        if _get_aumid is not None:
            length = ctypes.c_uint32(512)
            id_buf = ctypes.create_unicode_buffer(length.value)
            if _get_aumid(handle, ctypes.byref(length), id_buf) == 0:
                aumid = id_buf.value or None
        return path, aumid
    finally:
        kernel32.CloseHandle(handle)


def _uwp_child_pid(hwnd: int) -> Optional[int]:
    """UWP apps are hosted by ApplicationFrameHost.exe; the real process owns
    the inner CoreWindow."""
    found: list[int] = []

    def callback(child, _lparam):
        try:
            if _text(user32.GetClassNameW, child, 128) == "Windows.UI.Core.CoreWindow":
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(child, ctypes.byref(pid))
                if pid.value:
                    found.append(pid.value)
                    return False
        except Exception:
            pass
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(callback), 0)
    return found[0] if found else None


def _command_lines() -> dict[int, str]:
    """pid -> command line, via CIM. Optional: an empty map just means we
    relaunch apps with their bare executable path."""
    script = ("Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=25, text=True,
            encoding="utf-8", errors="replace",
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        data = json.loads(out.stdout or "[]")
    except Exception:
        return {}
    if isinstance(data, dict):
        data = [data]
    result = {}
    for row in data:
        try:
            pid = int(row.get("ProcessId") or 0)
            cmd = row.get("CommandLine")
        except AttributeError:
            continue
        if pid and cmd:
            result[pid] = cmd
    return result


class WindowsBackend:
    name = "win"

    CMDLINE_TTL = 30.0  # seconds; the UI process is long lived

    def __init__(self) -> None:
        enable_dpi_awareness()
        self._cmdlines: Optional[dict[int, str]] = None
        self._cmdlines_at = 0.0
        self._workspace_offset: Optional[tuple[int, int]] = None

    # -- displays -------------------------------------------------------------
    def monitors(self) -> list[MonitorInfo]:
        found: list[MonitorInfo] = []

        def callback(hmonitor, _hdc, _rect_ptr, _lparam):
            try:
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
                    found.append(MonitorInfo(
                        device=info.szDevice,
                        rect=_rect(info.rcMonitor),
                        work=_rect(info.rcWork),
                        primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                        dpi=self._monitor_dpi(hmonitor),
                    ))
            except Exception:
                pass
            return True

        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
        found.sort(key=lambda m: (not m.primary, m.rect.left, m.rect.top))
        for index, mon in enumerate(found):
            mon.index = index
        return found

    def _monitor_dpi(self, hmonitor) -> int:
        if shcore is None:
            return 96
        x, y = ctypes.c_uint(96), ctypes.c_uint(96)
        try:
            shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(x), ctypes.byref(y))
        except Exception:
            return 96
        return int(x.value or 96)

    def _offset(self) -> tuple[int, int]:
        """Screen -> workspace delta (non zero only for a top/left taskbar)."""
        if self._workspace_offset is None:
            self._workspace_offset = (0, 0)
            for mon in self.monitors():
                if mon.primary:
                    self._workspace_offset = (mon.work.left - mon.rect.left,
                                              mon.work.top - mon.rect.top)
                    break
        return self._workspace_offset

    def _to_workspace(self, rect: Rect) -> Rect:
        dx, dy = self._offset()
        return rect.offset(-dx, -dy)

    def _from_workspace(self, rect: Rect) -> Rect:
        dx, dy = self._offset()
        return rect.offset(dx, dy)

    # -- windows --------------------------------------------------------------
    def windows(self, with_cmdlines: bool = True) -> list[WindowInfo]:
        handles: list[int] = []

        def callback(hwnd, _lparam):
            handles.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)  # front-most first

        if with_cmdlines and (self._cmdlines is None
                              or time.time() - self._cmdlines_at > self.CMDLINE_TTL):
            self._cmdlines = _command_lines()
            self._cmdlines_at = time.time()
        cmdlines = self._cmdlines or {}

        monitors = self.monitors()
        foreground = user32.GetForegroundWindow()
        result: list[WindowInfo] = []
        for hwnd in handles:
            info = self._describe(hwnd, monitors, cmdlines)
            if info is None:
                continue
            info.z = len(result)
            info.focused = bool(hwnd) and hwnd == foreground
            result.append(info)
        return result

    def _describe(self, hwnd, monitors, cmdlines) -> Optional[WindowInfo]:
        try:
            if not user32.IsWindowVisible(hwnd):
                return None
            if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
                return None
            if user32.GetWindow(hwnd, GW_OWNER):
                return None  # dialogs and palettes follow their owner

            ex_style = _get_window_long(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW and not ex_style & WS_EX_APPWINDOW:
                return None

            cls = _text(user32.GetClassNameW, hwnd, 256)
            if cls in SKIP_CLASSES:
                return None
            if _is_cloaked(hwnd):
                return None

            title = _text(user32.GetWindowTextW, hwnd, 1024).strip()
            if not title or title in SKIP_TITLES:
                return None

            rect_buf = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect_buf)):
                return None
            rect = _rect(rect_buf)

            placement = WINDOWPLACEMENT()
            placement.length = ctypes.sizeof(WINDOWPLACEMENT)
            normal = rect
            state = STATE_NORMAL
            if user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
                normal = self._from_workspace(_rect(placement.rcNormalPosition))
                if placement.showCmd == SW_SHOWMINIMIZED:
                    state = STATE_MINIMIZED
                elif placement.showCmd == SW_SHOWMAXIMIZED:
                    state = STATE_MAXIMIZED
            if state == STATE_MINIMIZED:
                rect = normal  # a minimized window reports (-32000, -32000)
            if rect.width <= 0 or rect.height <= 0:
                return None

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            real_pid = pid.value
            if cls == "ApplicationFrameWindow":
                real_pid = _uwp_child_pid(hwnd) or real_pid
            exe, aumid = _process_path(real_pid)

            monitor = None
            for mon in monitors:
                if (mon.rect.left <= rect.cx < mon.rect.right
                        and mon.rect.top <= rect.cy < mon.rect.bottom):
                    monitor = mon.device
                    break

            return WindowInfo(
                title=title,
                cls=cls,
                exe=exe,
                exe_name=os.path.basename(exe) if exe else None,
                aumid=aumid,
                cmdline=cmdlines.get(real_pid),
                rect=rect,
                normal_rect=normal,
                state=state,
                topmost=bool(ex_style & WS_EX_TOPMOST),
                monitor=monitor,
                hwnd=int(hwnd),
                pid=real_pid,
            )
        except Exception:
            return None

    def is_alive(self, win: WindowInfo) -> bool:
        return bool(win.hwnd and user32.IsWindow(win.hwnd) and user32.IsWindowVisible(win.hwnd))

    # -- moving ---------------------------------------------------------------
    def apply(self, win: WindowInfo, rect: Rect, state: str, topmost: bool) -> Optional[str]:
        hwnd = win.hwnd
        if not user32.IsWindow(hwnd):
            return "النافذة اتقفلت قبل ما نظبّطها"

        ctypes.set_last_error(0)
        try:
            if state == STATE_MINIMIZED:
                ok = self._place(hwnd, rect, SW_SHOWMINNOACTIVE)
            elif state == STATE_MAXIMIZED:
                # Restore first so the window carries the saved geometry, put it
                # on the target monitor, and only then maximize -- otherwise it
                # maximizes wherever it happened to be.
                ok = self._place(hwnd, rect, SW_SHOWNOACTIVATE) and self._move(hwnd, rect)
                user32.ShowWindow(hwnd, SW_MAXIMIZE)  # return value is not an error flag
            else:
                if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
                    self._place(hwnd, rect, SW_SHOWNOACTIVATE)
                ok = self._move(hwnd, rect)
        except Exception as exc:  # pragma: no cover - defensive
            return f"خطأ غير متوقع: {exc}"

        # Read the error code before any other call overwrites it.
        code = 0 if ok else ctypes.get_last_error()
        self._set_topmost(hwnd, topmost)

        if not ok:
            if code == ERROR_ACCESS_DENIED:
                return "النافذة دي بتشتغل بصلاحيات أدمن — شغّل البرنامج كمسؤول"
            if code:
                return f"ويندوز رفض التحريك (خطأ {code})"
        return None

    def _place(self, hwnd, rect: Rect, show_cmd: int) -> bool:
        placement = WINDOWPLACEMENT()
        placement.length = ctypes.sizeof(WINDOWPLACEMENT)
        if not user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
            return False
        workspace = self._to_workspace(rect)
        placement.showCmd = show_cmd
        placement.rcNormalPosition = wintypes.RECT(
            workspace.left, workspace.top, workspace.right, workspace.bottom)
        return bool(user32.SetWindowPlacement(hwnd, ctypes.byref(placement)))

    def _move(self, hwnd, rect: Rect) -> bool:
        return bool(user32.SetWindowPos(
            hwnd, None, rect.left, rect.top, rect.width, rect.height,
            SWP_NOZORDER | SWP_NOACTIVATE))

    def _set_topmost(self, hwnd, topmost: bool) -> None:
        current = bool(_get_window_long(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
        if current == topmost:
            return
        user32.SetWindowPos(hwnd, HWND_TOPMOST if topmost else HWND_NOTOPMOST,
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def raise_window(self, win: WindowInfo) -> None:
        if user32.IsWindow(win.hwnd):
            user32.SetWindowPos(win.hwnd, HWND_TOP, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def focus(self, win: WindowInfo) -> None:
        """Foreground stealing is restricted; attaching to the current
        foreground thread is the usual way around it."""
        hwnd = win.hwnd
        if not user32.IsWindow(hwnd):
            return
        try:
            current = user32.GetForegroundWindow()
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)
            this_thread = kernel32.GetCurrentThreadId()
            fg_thread = user32.GetWindowThreadProcessId(current, None) if current else 0
            attached = False
            if fg_thread and fg_thread != this_thread:
                attached = bool(user32.AttachThreadInput(this_thread, fg_thread, True))
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            if attached:
                user32.AttachThreadInput(this_thread, fg_thread, False)
            del target_thread
        except Exception:
            pass

    # -- launching ------------------------------------------------------------
    def launch(self, spec: WindowInfo) -> Optional[str]:
        if spec.aumid:
            return self._spawn(["explorer.exe", f"shell:AppsFolder\\{spec.aumid}"], None)
        if not spec.exe:
            return "مش عارفين البرنامج اللي بيفتح النافذة دي"
        if not os.path.exists(spec.exe):
            return f"الملف مش موجود: {spec.exe}"
        workdir = os.path.dirname(spec.exe) or None
        command = self._launch_command(spec)
        return self._spawn(command, workdir)

    @staticmethod
    def _launch_command(spec: WindowInfo):
        """Prefer the captured command line, but only when it really is this
        executable being started (so we never replay a helper process)."""
        cmd = (spec.cmdline or "").strip()
        if cmd and spec.exe and len(cmd) < 2000:
            head = cmd[1:].split('"', 1)[0] if cmd.startswith('"') else cmd.split(" ", 1)[0]
            if head.lower() == spec.exe.lower():
                return cmd
        return [spec.exe]

    @staticmethod
    def _spawn(command, workdir) -> Optional[str]:
        """Detached, so closing WindowLayout never takes the app down with it.

        Breaking away from the job object is the nice-to-have half: when the
        job forbids it CreateProcess fails outright, so retry without it.
        """
        base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        for flags in (base | CREATE_BREAKAWAY_FROM_JOB, base):
            try:
                subprocess.Popen(
                    command, cwd=workdir, close_fds=True, creationflags=flags,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return None
            except OSError as exc:
                error = exc
        return f"فشل التشغيل: {error}"

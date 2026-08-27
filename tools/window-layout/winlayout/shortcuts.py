"""Desktop shortcuts: the actual "one click" part of the app.

A shortcut runs the app with ``restore <layout>`` and nothing else, so it can
be double clicked or pinned to the taskbar. Packaged as an .exe that is the
exe itself; from source it is ``pythonw.exe winlayout-cli.py``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple, Optional

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


def desktop_dir() -> Path:
    profile = os.environ.get("USERPROFILE") or str(Path.home())
    for name in ("Desktop", "سطح المكتب", "OneDrive/Desktop"):
        candidate = Path(profile) / name
        if candidate.is_dir():
            return candidate
    return Path(profile)


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
    target = directory / f"{slugify(layout_name)}.lnk"
    command = shortcut_command(layout_name)

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
    except (OSError, subprocess.SubprocessError):
        pass
    return _create_cmd(layout_name, directory, command)


def _create_cmd(layout_name: str, directory: Path, command: Command) -> Path:
    target = directory / f"{slugify(layout_name)}.cmd"
    target.write_text(
        "@echo off\r\n"
        f'start "" "{command.target}" {command.arguments}\r\n',
        encoding="utf-8-sig",
    )
    return target

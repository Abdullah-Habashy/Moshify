"""Where layouts live on disk: %APPDATA%\\WindowLayout\\layouts\\*.json"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from .model import Layout, slugify


def home_dir() -> Path:
    override = os.environ.get("WINLAYOUT_HOME")
    if override:
        return Path(override)
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "WindowLayout"
    return Path.home() / ".config" / "winlayout"


def layouts_dir() -> Path:
    path = home_dir() / "layouts"
    path.mkdir(parents=True, exist_ok=True)
    return path


class LayoutStore:
    def __init__(self, directory: Optional[Path] = None):
        self.directory = Path(directory) if directory else layouts_dir()
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        return self.directory / f"{slugify(name)}.json"

    def names(self) -> list[str]:
        out = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append(data.get("name") or path.stem)
        return out

    def all(self) -> list[Layout]:
        layouts = []
        for path in sorted(self.directory.glob("*.json")):
            layout = self._read(path)
            if layout is not None:
                layouts.append(layout)
        layouts.sort(key=lambda l: l.updated_at, reverse=True)
        return layouts

    def get(self, name: str) -> Optional[Layout]:
        return self._read(self.path_for(name))

    def exists(self, name: str) -> bool:
        return self.path_for(name).exists()

    def save(self, layout: Layout) -> Path:
        layout.updated_at = time.time()
        path = self.path_for(layout.name)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(layout.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return path

    def delete(self, name: str) -> bool:
        path = self.path_for(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def rename(self, old: str, new: str) -> Optional[Layout]:
        layout = self.get(old)
        if layout is None:
            return None
        old_path = self.path_for(old)
        layout.name = new
        self.save(layout)
        if self.path_for(new) != old_path and old_path.exists():
            old_path.unlink()
        return layout

    def _read(self, path: Path) -> Optional[Layout]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        layout = Layout.from_dict(data)
        if not layout.name:
            layout.name = path.stem
        return layout

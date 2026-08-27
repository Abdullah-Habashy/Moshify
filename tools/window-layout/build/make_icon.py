"""Generate winlayout/ui/icon.ico from code — no image library needed.

The .ico holds PNG-compressed frames, which every Windows since Vista reads.
Run it only when the logo changes; the generated file is committed.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
BLUE = (37, 99, 235)
BLUE_DARK = (29, 78, 216)
WHITE = (255, 255, 255)

# The logo, in a 24x24 grid: one tall panel plus two stacked ones.
PANELS = ((2, 3, 11, 21), (13, 3, 22, 11), (13, 13, 22, 21))
RADIUS = 2.0


def _inside_round_rect(x: float, y: float, box, radius: float) -> float:
    """Coverage of a pixel centre, softened at the corners for anti-aliasing."""
    left, top, right, bottom = box
    cx = min(max(x, left + radius), right - radius)
    cy = min(max(y, top + radius), bottom - radius)
    if left <= x <= right and top <= y <= bottom:
        distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
        return max(0.0, min(1.0, radius - distance + 0.5)) if distance > 0 else 1.0
    return 0.0


def _render(size: int) -> bytes:
    """RGBA rows for one icon size, supersampled 3x3 for smooth edges."""
    scale = size / 24.0
    samples = 3
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            cover = 0.0
            for sy in range(samples):
                for sx in range(samples):
                    x = (px + (sx + 0.5) / samples) / scale
                    y = (py + (sy + 0.5) / samples) / scale
                    for panel in PANELS:
                        cover += _inside_round_rect(x, y, panel, RADIUS)
            cover = min(1.0, cover / (samples * samples))
            # A soft vertical gradient keeps it from looking flat at 256px.
            mix = py / max(1, size - 1)
            color = tuple(round(a + (b - a) * mix) for a, b in zip(BLUE, BLUE_DARK))
            alpha = round(cover * 255)
            row += bytes((*(color if alpha else WHITE), alpha))
        rows.append(bytes(row))
    return b"".join(b"\x00" + row for row in rows)


def _png(size: int) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(_render(size), 9))
            + chunk(b"IEND", b""))


def build(target: Path) -> Path:
    frames = [(size, _png(size)) for size in SIZES]
    offset = 6 + 16 * len(frames)
    directory, blobs = b"", b""
    for size, blob in frames:
        directory += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    target.write_bytes(struct.pack("<HHH", 0, 1, len(frames)) + directory + blobs)
    return target


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "winlayout" / "ui" / "icon.ico"
    print("wrote", build(out), out.stat().st_size, "bytes")

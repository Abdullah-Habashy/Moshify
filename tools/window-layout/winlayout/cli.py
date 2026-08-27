"""Command line: winlayout save|restore|list|show|delete|shortcut|ui"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from . import arabic
from .engine import Engine, STATUS_FAILED, STATUS_MISSING
from .store import LayoutStore


STATE_LABEL = {"normal": "عادية", "maximized": "مكبّرة", "minimized": "مصغّرة"}

def _print(text: str = "") -> None:
    """Print, degrading to '?' on a console that cannot hold Arabic.

    Round-tripping through the stream's *own* encoding is the part that
    matters: replacing into UTF-8 and decoding as ASCII produces U+FFFD,
    which a cp1252 console cannot encode either, so the fallback itself
    would raise.
    """
    stream = sys.stdout
    if stream is None:  # windowed .exe with nowhere to write
        return
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding, "replace"))


def cmd_list(args, store: LayoutStore, engine: Engine) -> int:
    layouts = store.all()
    if not layouts:
        _print("مافيش توزيعات محفوظة. احفظ واحد بـ:  winlayout save \"اسم التوزيع\"")
        return 0
    for layout in layouts:
        _print(f"• {layout.name}  ({arabic.windows(len(layout.windows))}، "
               f"{arabic.monitors(len(layout.monitors))})")
    return 0


def cmd_save(args, store: LayoutStore, engine: Engine) -> int:
    if store.exists(args.name) and not args.force:
        _print(f"التوزيع «{args.name}» موجود. استخدم --force عشان تستبدله.")
        return 1
    layout = engine.capture(args.name)
    if args.only:
        wanted = [w.lower() for w in args.only]
        layout.windows = [w for w in layout.windows
                          if any(term in (w.exe_name or "").lower()
                                 or term in w.title.lower() for term in wanted)]
    if not layout.windows:
        _print("مالقيناش نوافذ نحفظها.")
        return 1
    store.save(layout)
    _print(f"اتحفظ «{layout.name}» — {arabic.windows(len(layout.windows))}:")
    for win in layout.windows:
        _print(f"   - {win.describe()}")
    return 0


def cmd_restore(args, store: LayoutStore, engine: Engine) -> int:
    layout = store.get(args.name)
    if layout is None:
        _print(f"مافيش توزيع اسمه «{args.name}».")
        return 1
    if args.no_launch:
        layout.launch_missing = False
    report = engine.restore(layout, progress=_print if args.verbose else None)
    if not args.verbose:
        _print(report.summary())
    for result in report.results:
        if result.status in (STATUS_FAILED, STATUS_MISSING):
            _print(f"   ! {result.app} — {result.title}: {result.message}")
    for warning in report.warnings:
        _print(f"   ⚠ {warning}")
    return 0 if report.ok else 2


def cmd_show(args, store: LayoutStore, engine: Engine) -> int:
    layout = store.get(args.name)
    if layout is None:
        _print(f"مافيش توزيع اسمه «{args.name}».")
        return 1
    _print(f"«{layout.name}» — {arabic.windows(len(layout.windows))}")
    # الأسطر اللي فيها أرقام بتفضل لاتينية بالكامل: لو خلطناها بعربي، الطرفية
    # بتقلب ترتيب المقاسات (1280×1040 بتبقى 1040×1280).
    _print()
    _print("الشاشات (* = الأساسية):")
    for mon in layout.monitors:
        flag = " *" if mon.primary else ""
        _print(f"  [{mon.index}] {mon.rect.width}×{mon.rect.height}{flag}")
    _print()
    _print("النوافذ:")
    for win in layout.windows:
        rect = win.rect
        _print(f"  • {win.describe()}   ({STATE_LABEL.get(win.state, win.state)})")
        _print(f"      {rect.width}×{rect.height} @ ({rect.left}, {rect.top})")
    return 0


def cmd_delete(args, store: LayoutStore, engine: Engine) -> int:
    if store.delete(args.name):
        _print(f"اتمسح «{args.name}».")
        return 0
    _print(f"مافيش توزيع اسمه «{args.name}».")
    return 1


def cmd_shortcut(args, store: LayoutStore, engine: Engine) -> int:
    from .shortcuts import create_shortcut
    if not store.exists(args.name):
        _print(f"مافيش توزيع اسمه «{args.name}».")
        return 1
    path = create_shortcut(args.name)
    _print(f"الاختصار اتعمل: {path}")
    return 0


def cmd_ui(args, store: LayoutStore, engine: Engine) -> int:
    from .ui.server import serve
    serve(open_browser=not args.no_browser, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="winlayout",
        description="احفظ توزيع النوافذ على الشاشة ورجّعه بضغطة واحدة.")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("list", help="التوزيعات المحفوظة")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("save", help="احفظ توزيع النوافذ الحالي")
    p.add_argument("name")
    p.add_argument("--force", action="store_true", help="استبدل توزيع بنفس الاسم")
    p.add_argument("--only", nargs="+", metavar="TERM",
                   help="احفظ النوافذ اللي فيها الكلمات دي بس")
    p.set_defaults(func=cmd_save)

    p = sub.add_parser("restore", help="رجّع توزيع محفوظ")
    p.add_argument("name")
    p.add_argument("--no-launch", action="store_true",
                   help="متفتحش البرامج المقفولة، ظبّط المفتوح بس")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("show", help="تفاصيل توزيع")
    p.add_argument("name")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("delete", help="امسح توزيع")
    p.add_argument("name")
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("shortcut", help="اعمل اختصار على الديسكتوب")
    p.add_argument("name")
    p.set_defaults(func=cmd_shortcut)

    p = sub.add_parser("ui", help="افتح الواجهة")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_ui)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    store = LayoutStore()
    engine = None
    if args.func is not cmd_ui:
        try:
            engine = Engine()
        except RuntimeError as exc:
            _print(str(exc))
            return 1
    try:
        return args.func(args, store, engine)
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

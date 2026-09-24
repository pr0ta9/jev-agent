"""nyx "message" [files...] [--withhold-tools]   ·   nyx --accept <trace>"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import loop
from .settings import load


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nyx")
    ap.add_argument("message", nargs="?")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--withhold-tools", action="store_true")
    ap.add_argument("--accept", metavar="TRACE")
    args = ap.parse_args(argv)
    settings = load()
    if args.accept:
        from .learn import accept
        print(accept(Path(args.accept), settings))
        return 0
    if not args.message:
        ap.error("a message is required")
    out = loop.run(args.message, [Path(f) for f in args.files], loop.Deps(settings=settings), withhold_tools=args.withhold_tools)
    sys.stdout.reconfigure(encoding="utf-8")
    print(out["reply"])
    print(f"[{out['exit']}] trace: {out['trace']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

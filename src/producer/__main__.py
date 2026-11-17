"""Entry point: python -m producer <command>."""
from __future__ import annotations

import sys

USAGE = """usage: python -m producer <command>

  doctor [--fetch] [--full]   check this machine; --fetch downloads the models
  produce <script.md> [--slug S] [--variant NAME]
                              build final.mp4 + final.srt + manifest.json in runs/
  approve <run_id> [--by N] [--note "text"]
                              set approved=true (the human only, after watching the video)
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "doctor":
        from .doctor import main as doctor
        return doctor(rest)
    if cmd == "produce":
        from .pipeline import main as produce
        return produce(rest)
    if cmd == "approve":
        from .approve import main as approve
        return approve(rest)
    print(f"unknown command: {cmd}\n\n{USAGE}")
    return 2


if __name__ == "__main__":
    sys.exit(main())

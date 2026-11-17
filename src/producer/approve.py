"""`python -m producer approve <run_id> [--by NAME] [--note "..."]`

Sets approved=true in runs/<run_id>/manifest.json and records who, when and the
sha256 of the approved final.mp4. If final.mp4 changes afterwards (another pass), the approval
no longer holds: `produce` rewrites the manifest with approved=false and the Publisher
compares the hash before uploading. Only the human runs this.
"""
from __future__ import annotations

import datetime as dt
import getpass
import json
import os
import subprocess
from pathlib import Path

from .config import load_config, runs_root
from .manifest import sha256_file


def _default_approver() -> str:
    try:
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        if name:
            return name
    except OSError:
        pass
    return getpass.getuser()


def approve(run_id: str, by: str | None = None, note: str | None = None,
            variant: str | None = None, root: Path | None = None) -> dict:
    """variant: None/"main" -> manifest.json + final.mp4; "fast" -> manifest_fast.json + final_fast.mp4.
    root: runs folder (default: config.toml paths.runs); the Telegram bot tests pass a copy."""
    run_dir = (root or runs_root(load_config())) / run_id
    sfx = f"_{variant}" if variant and variant != "main" else ""
    mf, video = run_dir / f"manifest{sfx}.json", run_dir / f"final{sfx}.mp4"
    if not mf.exists():
        raise SystemExit(f"not found: {mf}")
    data = json.loads(mf.read_text(encoding="utf-8"))
    if data.get("status") != "done":
        raise SystemExit(f"the run is in state '{data.get('status')}'; only a 'done' run can be approved")
    if not video.exists():
        raise SystemExit(f"not found: {video}")
    data["approved"] = True
    data["approval"] = {
        "by": by or _default_approver(),
        "at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "final_mp4_sha256": sha256_file(video),
        "pass": data.get("pass"),
        "note": note,
    }
    tmp = mf.with_name(".manifest.json.writing")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, mf)
    return data["approval"]


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print('usage: python -m producer approve <run_id> [--by NAME] [--note "text"] [--variant NAME]')
        return 2
    by = argv[argv.index("--by") + 1] if "--by" in argv else None
    note = argv[argv.index("--note") + 1] if "--note" in argv else None
    variant = argv[argv.index("--variant") + 1] if "--variant" in argv else None
    a = approve(argv[0], by, note, variant=variant)
    print(f"APPROVED {argv[0]} by {a['by']} at {a['at']}\nfinal.mp4 sha256 {a['final_mp4_sha256'][:16]}... (pass {a['pass']})")
    return 0

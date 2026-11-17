"""Workspace for one run.

Synced-folder rule: every intermediate file is written to tmp_dir (local, outside the synced folder).
Only final outputs move to runs/<run_id>/ with an atomic move when each stage
closes, so a sync client never sees a half-written file.
"""
from __future__ import annotations

import datetime as dt
import errno
import json
import os
import shutil
import time
from pathlib import Path

from .config import runs_root, tmp_root

_ERROR_NOT_SAME_DEVICE = 17  # WinError al mover entre volúmenes


def atomic_move(src: Path, dest: Path, retries: int = 5) -> None:
    """Moves src to dest atomically.

    Same volume: os.replace (atomic rename). Different volume: copy to
    dest.partial, then os.replace. Retries if a sync client has the destination
    locked while uploading it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            try:
                os.replace(src, dest)
            except OSError as e:
                if getattr(e, "winerror", None) != _ERROR_NOT_SAME_DEVICE and e.errno != errno.EXDEV:
                    raise
                partial = dest.with_name(dest.name + ".partial")
                shutil.copy2(src, partial)
                os.replace(partial, dest)
                src.unlink()
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(1.0 + attempt)


class RunWorkspace:
    def __init__(self, slug: str, cfg: dict, date: str | None = None):
        date = date or dt.date.today().isoformat()
        self.run_id = f"{date}_{slug}"
        self.final_dir = runs_root(cfg) / self.run_id
        self.tmp_dir = tmp_root() / self.run_id
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.final_dir.mkdir(parents=True, exist_ok=True)

    def tmp(self, *parts: str) -> Path:
        """Path inside the temp folder (creates the parent folders)."""
        p = self.tmp_dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def publish(self, src: Path, rel: str | None = None) -> Path:
        """Moves a final output from tmp to runs/<run_id>/rel."""
        dest = self.final_dir / (rel or src.name)
        atomic_move(src, dest)
        return dest

    def write_json(self, rel: str, data: dict) -> Path:
        """Writes JSON to tmp and publishes it atomically (safe for rewrites)."""
        p = self.tmp(f".{rel}.writing")
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return self.publish(p, rel)

    def clean_tmp(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

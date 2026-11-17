"""Loads config.toml + .env and resolves the project paths."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """Loads .env when this module is imported, before huggingface_hub (which reads HF_HOME
    on import). An empty variable in .env is dropped: HF_HOME="" would make the models
    download into the current folder."""
    load_dotenv(PROJECT_ROOT / ".env")
    for var in ("HF_HOME", "TBL_TMP_DIR"):
        if var in os.environ and not os.environ[var].strip():
            del os.environ[var]
    # Silencia el aviso de symlinks de huggingface_hub en Windows sin Modo desarrollador.
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _refresh_windows_path() -> None:
    """A terminal opened before installing FFmpeg/OBS has a stale PATH.
    Adds the missing registry entries (system + user) to this process's PATH."""
    if sys.platform != "win32":
        return
    import winreg

    def read(root, key: str) -> str:
        try:
            with winreg.OpenKey(root, key) as k:
                return winreg.QueryValueEx(k, "Path")[0]
        except OSError:
            return ""

    reg = read(winreg.HKEY_LOCAL_MACHINE,
               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    reg += ";" + read(winreg.HKEY_CURRENT_USER, "Environment")
    current = os.environ.get("PATH", "").split(os.pathsep)
    seen = {p.rstrip("\\").lower() for p in current if p}
    extra = []
    for p in reg.split(";"):
        p = os.path.expandvars(p.strip())
        if p and p.rstrip("\\").lower() not in seen:
            seen.add(p.rstrip("\\").lower())
            extra.append(p)
    if extra:
        os.environ["PATH"] = os.pathsep.join(current + extra)


_load_env()
_refresh_windows_path()


def load_config() -> dict:
    with open(PROJECT_ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


def runs_root(cfg: dict) -> Path:
    """Final outputs: inside the project (the synced folder)."""
    return PROJECT_ROOT / cfg["paths"]["runs"]


def tmp_root() -> Path:
    """Intermediate files: local folder outside the synced folder."""
    env = os.environ.get("TBL_TMP_DIR", "").strip()
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "tbl-tmp"

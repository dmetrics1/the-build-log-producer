"""Per-run manifest.json: prompts, models, voice, seeds, timings, VRAM and costs.

Each stage runs through run_stage(): it measures time and peak VRAM, retries
up to 3 times and, if all 3 fail, marks the stage as failed and stops the
run (channel rule). The manifest is published when each stage closes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import platform
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from .workspace import RunWorkspace

SCHEMA_VERSION = 1
# nombres de campo que delatan una credencial (no "keyword", "keywords", etc.)
_SECRET_KEY = re.compile(r"(^|_)(api_?key|access_?key|private_?key|secret|password|passwd|token|auth)$", re.I)


class StageFailed(RuntimeError):
    """A stage failed 3 times: the run stops and reports it."""


def _now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _nvidia_smi(fields: str) -> list[str] | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return [x.strip() for x in out.strip().splitlines()[0].split(",")]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


class VramSampler(threading.Thread):
    """Samples whole-machine resources every second: VRAM used (nvidia-smi, any
    process), CPU % and RAM used (psutil, if installed)."""

    def __init__(self, interval: float = 1.0):
        super().__init__(daemon=True)
        self.interval, self.peak, self._stop_evt = interval, 0, threading.Event()
        self.cpu: list[float] = []
        self.ram_peak_gb = 0.0
        try:
            import psutil
            self._ps = psutil
            psutil.cpu_percent(None)
        except ImportError:
            self._ps = None

    def run(self) -> None:
        while not self._stop_evt.is_set():
            v = _nvidia_smi("memory.used")
            if v:
                self.peak = max(self.peak, int(v[0]))
            if self._ps:
                self.cpu.append(self._ps.cpu_percent(None))
                self.ram_peak_gb = max(self.ram_peak_gb, self._ps.virtual_memory().used / 2**30)
            self._stop_evt.wait(self.interval)

    def stop(self) -> int:
        self._stop_evt.set()
        self.join(timeout=5)
        return self.peak

    def stats(self) -> dict:
        if not self.cpu:
            return {}
        return {"cpu_avg_pct": round(sum(self.cpu) / len(self.cpu), 1), "cpu_peak_pct": round(max(self.cpu), 1),
                "ram_peak_gb": round(self.ram_peak_gb, 1)}


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("***" if _SECRET_KEY.search(str(k)) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def host_info() -> dict:
    info = {"os": platform.platform(), "python": platform.python_version()}
    gpu = _nvidia_smi("name,driver_version,memory.total")
    if gpu:
        info.update(gpu=gpu[0], driver=gpu[1], vram_total_mib=int(gpu[2]))
    if "torch" in sys.modules:
        torch = sys.modules["torch"]
        info.update(torch=torch.__version__, torch_cuda=torch.version.cuda)
    return info


class Manifest:
    def __init__(self, ws: RunWorkspace, cfg: dict, slug: str, filename: str = "manifest.json"):
        self.ws = ws
        self.filename = filename
        self.data: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": ws.run_id,
            "slug": slug,
            "created_at": _now(),
            "approved": False,          # solo el humano lo pone en true
            "approval": {"by": None, "at": None},
            "status": "running",
            "host": host_info(),
            "config": cfg,
            "inputs": {},
            "prompts": [],              # prompts de LLM usados (guion, etc.)
            "models": {},
            "voice": {},
            "seeds": {},
            "stages": [],
            "outputs": {},
            "costs": {},
            "notes": [],
        }

    def save(self) -> Path:
        return self.ws.write_json(self.filename, _redact(self.data))

    def run_stage(self, name: str, fn: Callable[[dict], Any], attempts: int = 3, **details) -> Any:
        """Runs fn(rec) measuring time and VRAM; up to `attempts` attempts."""
        rec: dict[str, Any] = {"name": name, "status": "running", "started_at": _now(),
                               "attempts": [], **details}
        self.data["stages"].append(rec)
        sampler = VramSampler()
        sampler.start()
        t0 = time.perf_counter()
        try:
            for i in range(1, attempts + 1):
                ta = time.perf_counter()
                try:
                    result = fn(rec)
                    rec["attempts"].append({"n": i, "ok": True,
                                            "seconds": round(time.perf_counter() - ta, 2)})
                    rec["status"] = "ok"
                    return result
                except Exception as e:  # noqa: BLE001 — se registra y se reintenta
                    rec["attempts"].append({"n": i, "ok": False,
                                            "seconds": round(time.perf_counter() - ta, 2),
                                            "error": f"{type(e).__name__}: {e}",
                                            "trace": traceback.format_exc(limit=5)})
            rec["status"] = "failed"
            self.data["status"] = "failed"
            raise StageFailed(f"Stage '{name}' failed {attempts} times: "
                              f"{rec['attempts'][-1]['error']}")
        finally:
            rec["seconds"] = round(time.perf_counter() - t0, 2)
            rec["vram_peak_mib"] = sampler.stop()
            rec.update(sampler.stats())
            rec["ended_at"] = _now()
            self.save()

    def finish(self) -> Path:
        """Closes the run. If it succeeded, deletes the intermediate files in the temp
        folder; if it failed, keeps them for diagnosis."""
        if self.data["status"] == "running":
            self.data["status"] = "done"
        self.data["finished_at"] = _now()
        self.data["total_seconds"] = round(sum(s.get("seconds", 0) for s in self.data["stages"]), 2)
        ok = self.data["status"] == "done"
        self.data["tmp_dir"] = {"path": str(self.ws.tmp_dir), "cleaned": ok}
        path = self.save()
        if ok:
            self.ws.clean_tmp()
        return path

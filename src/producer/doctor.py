"""`python -m producer doctor`: checks that this machine can run the Producer.

--fetch  downloads the models (Kokoro, channel voice, whisper, explainroo) into their caches.
--full   also runs `explainroo doctor` (slower).
Never prints .env values.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT, load_config, runs_root, tmp_root

OK, WARN, FAIL = "OK", "WARN", "FAIL"
OBS_DEFAULT = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
EXPLAINROO_MODELS = Path.home() / ".cache" / "explainroo" / "models"
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], timeout: int = 60, env: dict | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env=env, creationflags=_NOWIN, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout.strip() or p.stderr.strip())
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


def _ver(s: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", s)
    return tuple(int(x) for x in m.groups() if x is not None) if m else ()


def _tool(name: str, args: list[str], minimum: tuple[int, ...] | None = None,
          missing: str = FAIL) -> tuple[str, str, str]:
    path = shutil.which(name)
    if not path:
        return missing, name, "not in PATH"
    code, out = _run([path, *args])
    first = out.splitlines()[0] if out else ""
    if code != 0:
        return FAIL, name, f"failed to run: {first}"
    if minimum and _ver(first) < minimum:
        return FAIL, name, f"{first} (requires >= {'.'.join(map(str, minimum))})"
    return OK, name, first[:90]


def check_python() -> tuple[str, str, str]:
    env = os.environ.get("CONDA_DEFAULT_ENV") or Path(sys.prefix).name
    v = sys.version_info[:2]
    st = OK if (v == (3, 11) and env == "tbl") else (WARN if v == (3, 11) else FAIL)
    return st, "python", f"{platform.python_version()} (conda env: {env})"


def check_obs() -> tuple[str, str, str]:
    path = shutil.which("obs64")
    if path:
        return OK, "obs", path  # no se ejecuta: abriría la ventana de OBS
    if OBS_DEFAULT.exists():
        return WARN, "obs", "installed but not in this terminal's PATH (restart VS Code)"
    return WARN, "obs", "not installed (only needed for screen recording)"


def check_gpu() -> tuple[str, str, str]:
    code, out = _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used",
                      "--format=csv,noheader"])
    return (OK, "gpu", out) if code == 0 else (FAIL, "gpu", f"nvidia-smi failed: {out[:80]}")


def check_torch() -> tuple[str, str, str]:
    try:
        import torch
    except ImportError as e:
        return FAIL, "torch", f"import failed: {e}"
    if not torch.cuda.is_available():
        return FAIL, "torch", f"{torch.__version__}: CUDA not available (cu128 wheel?)"
    cap = torch.cuda.get_device_capability(0)
    arch = f"sm_{cap[0]}{cap[1]}"
    free, total = torch.cuda.mem_get_info()
    st = OK if arch in torch.cuda.get_arch_list() else FAIL
    return st, "torch", (f"{torch.__version__} | {torch.cuda.get_device_name(0)} | {arch} | "
                         f"VRAM free {free / 2**30:.1f}/{total / 2**30:.1f} GB")


def _hf_cached(repo: str, filename: str) -> bool:
    from huggingface_hub import try_to_load_from_cache
    return isinstance(try_to_load_from_cache(repo, filename), str)


def check_kokoro(cfg: dict) -> tuple[str, str, str]:
    try:
        import kokoro  # noqa: F401
    except ImportError as e:
        return FAIL, "kokoro", f"import failed: {e}"
    repo, voice = cfg["voice"]["model"], cfg["voice"]["voice"]
    missing = [f for f in ("kokoro-v1_0.pth", "config.json", f"voices/{voice}.pt")
               if not _hf_cached(repo, f)]
    if missing:
        return WARN, "kokoro", f"missing from cache: {', '.join(missing)} (use --fetch)"
    return OK, "kokoro", f"{kokoro.__version__} | model and voice {voice} cached"


def check_whisper(cfg: dict) -> tuple[str, str, str]:
    try:
        import torch  # noqa: F401  carga cuBLAS/cuDNN de torch para ctranslate2
        import ctranslate2
        import faster_whisper
        from faster_whisper.utils import _MODELS
    except ImportError as e:
        return FAIL, "faster-whisper", f"import failed: {e}"
    n = ctranslate2.get_cuda_device_count()
    name = cfg["align"]["model"]
    cached = _hf_cached(_MODELS[name], "model.bin")
    st = OK if (n > 0 and cached) else (WARN if n > 0 else FAIL)
    return st, "faster-whisper", (f"{faster_whisper.__version__} | ctranslate2 {ctranslate2.__version__} "
                                  f"| GPUs CUDA: {n} | {name} {'cached' if cached else 'NOT cached (use --fetch)'}")


def check_explainroo(cfg: dict, full: bool) -> tuple[str, str, str]:
    npx = shutil.which("npx")
    if not npx:
        return FAIL, "explainroo", "npx not in PATH"
    if not EXPLAINROO_MODELS.exists():
        return WARN, "explainroo", "models not downloaded (use --fetch)"
    if full:
        code, out = _run([npx, "--yes", cfg["explain"]["package"], "doctor"], timeout=300,
                         env={**os.environ, "ONNXRUNTIME_NODE_INSTALL_CUDA": "skip"})
        bad = [ln for ln in out.splitlines() if ln.startswith(("missing", "error", "not ready"))]
        if code != 0 or bad:
            return FAIL, "explainroo", "; ".join(bad)[:120] or out[-120:]
    return OK, "explainroo", f"{cfg['explain']['package']} | models in {EXPLAINROO_MODELS}"


def check_dirs(cfg: dict) -> list[tuple[str, str, str]]:
    res = []
    for label, d in (("runs/ (the synced folder)", runs_root(cfg)), ("tmp (local)", tmp_root())):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".doctor_probe"
            probe.write_text("ok")
            probe.unlink()
            free = shutil.disk_usage(d).free / 2**30
            st = OK if free > 10 else WARN
            res.append((st, label, f"{d} | {free:.0f} GB free"))
        except OSError as e:
            res.append((FAIL, label, f"{d}: {e}"))
    same = Path(runs_root(cfg)).drive.lower() == tmp_root().drive.lower()
    res.append((OK if same else WARN, "atomic move",
                "tmp and runs on the same volume: atomic rename" if same
                else "different volumes: copy to .partial + rename"))
    return res


def check_env_file() -> tuple[str, str, str]:
    if (PROJECT_ROOT / ".env").exists():
        return OK, ".env", "present (values not shown)"
    return WARN, ".env", "missing; copy .env.example to .env (not needed to produce)"


def fetch(cfg: dict) -> None:
    from huggingface_hub import hf_hub_download
    repo, voice = cfg["voice"]["model"], cfg["voice"]["voice"]
    for f in ("config.json", "kokoro-v1_0.pth", f"voices/{voice}.pt"):
        print(f"  downloading {repo}/{f}")
        hf_hub_download(repo, f)
    print(f"  downloading whisper {cfg['align']['model']}")
    from faster_whisper import download_model
    download_model(cfg["align"]["model"])
    npx = shutil.which("npx")
    if npx:
        print(f"  {cfg['explain']['package']} doctor --fetch")
        subprocess.run([npx, "--yes", cfg["explain"]["package"], "doctor", "--fetch"],
                       env={**os.environ, "ONNXRUNTIME_NODE_INSTALL_CUDA": "skip"}, check=False)


def main(argv: list[str]) -> int:
    fetch_models, full = "--fetch" in argv, "--full" in argv
    cfg = load_config()
    if fetch_models:
        print("Downloading models into their caches (outside the project)...")
        fetch(cfg)
    checks = [
        check_python(),
        _tool("conda", ["--version"], missing=WARN),
        _tool("node", ["--version"], minimum=(20, 11)),
        _tool("npx", ["--version"]),
        _tool("ffmpeg", ["-hide_banner", "-version"]),
        _tool("ffprobe", ["-hide_banner", "-version"]),
        _tool("git", ["--version"], missing=WARN),
        check_obs(),
        check_gpu(),
        check_torch(),
        check_kokoro(cfg),
        check_whisper(cfg),
        check_explainroo(cfg, full),
        *check_dirs(cfg),
        check_env_file(),
    ]
    print(f"\nThe Build Log | producer doctor | channel voice: {cfg['voice']['voice']} "
          f"@ {cfg['voice']['speed']}x\n")
    for st, name, detail in checks:
        print(f"  {st:<5} {name:<17} {detail}")
    n_fail = sum(1 for c in checks if c[0] == FAIL)
    n_warn = sum(1 for c in checks if c[0] == WARN)
    print(f"\n{len(checks) - n_fail - n_warn} OK, {n_warn} WARN, {n_fail} FAIL")
    return 1 if n_fail else 0

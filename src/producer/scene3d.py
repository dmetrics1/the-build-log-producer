"""3D explainer scenes (PROTOTYPE): Three.js compositions rendered by Remotion (@remotion/three).

A complement to explainroo (2D diagrams), not a replacement: use 3D only where depth explains
something (structure, flow, comparison) that a flat diagram does not. Not wired into `produce` yet.

Layout (nothing heavy lives in the synced folder):
  src/producer/scene3d_project/         template: package.json + package-lock.json (exact pins), src/*.tsx
  <cache>/scene3d/deps-<hash>/          node_modules + Remotion's Chrome Headless Shell (keyed by the
                                        package files' hash, reused across runs)
  <cache>/scene3d/deps-<hash>/projects/<key>/   template copy + public/assets (fonts, sfx) -> bundled
  <cache>/scene3d/deps-<hash>/bundles/<key>/    webpack bundle (keyed by template + assets hash)
  <cache>/scene3d/clips/<comp>_<key>.mp4        normalised clips (content-hash cache)
  <workdir>/scene3d/<id>/                       props.json, render.log, raw Remotion output

Like explain.render_explain: THEME (theme_paper.scenes_theme) and METRICS are injected as input
props, duration = scene frames, timeout + 3 attempts, then the same COLOR_VF/COLOR_ARGS normalisation.
Usage: python -m producer.scene3d demo   (renders the demos to runs/scene3d_demo/)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import PROJECT_ROOT, tmp_root

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEMPLATE = Path(__file__).resolve().parent / "scene3d_project"
TEMPLATE_FILES = ("package.json", "package-lock.json", "tsconfig.json")
COMPOSITIONS = ("GpuMemory3D", "Pipeline3D", "Assembly3D")
CACHE_VERSION = "scene3d-v1"
# valores por defecto; un futuro [scene3d] en config.toml los sobreescribe
DEFAULTS = {
    # Medido 2026-11-16 (runs/scene3d_demo/README.md): vulkan = ANGLE sobre Vulkan en la RTX 5050 (la más
    # rápida); angle = D3D11 en el adaptador por defecto (Intel UHD en este portátil Optimus); egl y
    # angle-egl caen al Microsoft Basic Render Driver (software); swangle = SwiftShader (software, ~9× más lento).
    "gl": "vulkan",
    "gl_fallback": "angle",   # el ÚLTIMO intento usa este backend (registrado en attempts)
    "timeout_s": 300,         # por intento; un cuelgue cuenta como fallo
    "attempts": 3,
    "concurrency": 4,         # pestañas de Chrome renderizando a la vez
    "jpeg_quality": 95,
    "install_timeout_s": 900,
}


class Scene3DFailed(RuntimeError):
    pass


@dataclass
class Scene3D:
    """What render_scene3d needs (a future [EXPLAIN3D: ...] tag would build one of these)."""
    id: str
    composition: str
    frames: int
    aspect: str = "16:9"                       # "16:9" (1920×1080) | "9:16" (1080×1920, Shorts)
    data: dict = field(default_factory=dict)   # composition-specific: title, value, agents...
    index: int | None = None
    clip: Path | None = None


# ------------------------------------------------------------------ dependencias (node_modules + Chrome)

def _sha(*parts: bytes) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p)
    return h.hexdigest()[:12]


def deps_dir(cache_dir: Path) -> Path:
    key = _sha(*[(TEMPLATE / f).read_bytes() for f in ("package.json", "package-lock.json")])
    return Path(cache_dir) / "scene3d" / f"deps-{key}"


def cli(deps: Path) -> list[str]:
    """Local Remotion CLI (what `npx remotion` would run), with absolute paths."""
    return [shutil.which("node") or "node", str(deps / "node_modules" / "@remotion" / "cli" / "remotion-cli.js")]


def browser_exe(deps: Path) -> Path:
    return (deps / "node_modules" / ".remotion" / "chrome-headless-shell" / "win64" /
            "chrome-headless-shell-win64" / "chrome-headless-shell.exe")


def _dir_mb(p: Path) -> float:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / 2**20, 1)


def _run(cmd: list[str], cwd: Path, timeout: float, log: Path, env: dict | None = None) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8", errors="replace") as lf:
        p = subprocess.Popen(cmd, cwd=cwd, env=env or os.environ.copy(), stdout=lf, stderr=subprocess.STDOUT,
                             creationflags=_NOWIN)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=_NOWIN)
            p.wait(timeout=15)
            raise TimeoutError(f"{Path(cmd[1]).name if len(cmd) > 1 else cmd[0]} exceeded {timeout:.0f} s (killed)")
    if code != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-8:]
        raise Scene3DFailed(f"exit code {code}: {' | '.join(tail)}")


def ensure_deps(cache_dir: Path, opts: dict | None = None) -> Path:
    """node_modules (npm ci from the pinned lockfile) and Remotion's Chrome Headless Shell, once per hash."""
    o = {**DEFAULTS, **(opts or {})}
    d = deps_dir(cache_dir)
    marker = d / ".tbl-ready.json"
    if marker.exists() and browser_exe(d).exists():
        return d
    d.mkdir(parents=True, exist_ok=True)
    for f in ("package.json", "package-lock.json"):
        shutil.copy2(TEMPLATE / f, d / f)
    npm = shutil.which("npm") or "npm"
    t0 = time.perf_counter()
    if not (d / "node_modules" / "@remotion" / "cli").exists():
        _run([npm, "ci", "--no-audit", "--no-fund", "--loglevel=error"], d, o["install_timeout_s"], d / "install.log")
    t1 = time.perf_counter()
    # cwd = d: Remotion guarda el navegador en <carpeta con package.json>/node_modules/.remotion
    _run(cli(d) + ["browser", "ensure"], d, o["install_timeout_s"], d / "browser.log")
    marker.write_text(json.dumps({
        "npm_s": round(t1 - t0, 1), "browser_s": round(time.perf_counter() - t1, 1),
        "node_modules_mb": _dir_mb(d / "node_modules"),
        "browser_mb": _dir_mb(d / "node_modules" / ".remotion"),
    }, indent=1), encoding="utf-8")
    return d


def install_info(deps: Path) -> dict:
    try:
        return json.loads((deps / ".tbl-ready.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# ------------------------------------------------------------------ bundle (webpack) por plantilla + assets

def _public_assets() -> list[tuple[Path, str]]:
    """(source file, path under public/) for the theme's fonts and effects (same relative src as explainroo)."""
    from . import theme_paper
    return ([(f["path"], f["src"]) for f in theme_paper.font_assets()] +
            [(v["path"], v["src"]) for v in theme_paper.sfx_assets().values()])


def bundle_key() -> str:
    h = hashlib.sha1(CACHE_VERSION.encode())
    for f in sorted((TEMPLATE / "src").rglob("*")) + [TEMPLATE / n for n in TEMPLATE_FILES]:
        if f.is_file():
            h.update(f.relative_to(TEMPLATE).as_posix().encode())
            h.update(f.read_bytes())
    for src, rel in _public_assets():
        st = Path(src).stat()
        h.update(f"{rel}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()[:12]


def ensure_bundle(deps: Path, opts: dict | None = None) -> tuple[Path, float]:
    """Bundle the template once per (template, assets) hash. Returns (bundle dir, seconds spent)."""
    o = {**DEFAULTS, **(opts or {})}
    key = bundle_key()
    out = deps / "bundles" / key
    if (out / "index.html").exists():
        return out, 0.0
    # el proyecto vive DENTRO de deps/: webpack resuelve los módulos subiendo hasta deps/node_modules
    proj = deps / "projects" / key
    shutil.rmtree(proj, ignore_errors=True)
    shutil.copytree(TEMPLATE / "src", proj / "src")
    for n in TEMPLATE_FILES:
        shutil.copy2(TEMPLATE / n, proj / n)
    for src, rel in _public_assets():
        dst = proj / "public" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    tmp = deps / "bundles" / f"{key}.writing"
    shutil.rmtree(tmp, ignore_errors=True)
    t0 = time.perf_counter()
    _run(cli(deps) + ["bundle", "src/index.ts", f"--out-dir={tmp}", "--public-dir=public"], proj,
         o["timeout_s"], proj / "bundle.log")
    shutil.rmtree(out, ignore_errors=True)
    os.replace(tmp, out)
    # la copia del proyecto deja ~250 MB de caché de webpack (node_modules/.cache) que nunca se reutiliza
    # (cada clave es otra carpeta): se borra, y también los bundles de plantillas anteriores (~42 MB c/u)
    shutil.rmtree(proj, ignore_errors=True)
    for old in list((deps / "bundles").iterdir()) + list((deps / "projects").iterdir()):
        if old.is_dir() and old.name != key:
            shutil.rmtree(old, ignore_errors=True)
    return out, round(time.perf_counter() - t0, 2)


# ------------------------------------------------------------------ medición (VRAM, GPU, CPU)

class _Sampler(threading.Thread):
    """nvidia-smi (VRAM used + GPU utilisation of the NVIDIA GPU) and psutil CPU every 0.5 s."""

    def __init__(self, interval: float = 0.5):
        super().__init__(daemon=True)
        self.interval, self._stop_evt = interval, threading.Event()
        self.vram: list[int] = []
        self.util: list[int] = []
        self.cpu: list[float] = []
        try:
            import psutil
            self._ps = psutil
            psutil.cpu_percent(None)
        except ImportError:
            self._ps = None

    @staticmethod
    def query() -> tuple[int, int] | None:
        try:
            out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu",
                                           "--format=csv,noheader,nounits"], text=True, timeout=5,
                                          creationflags=_NOWIN)
            a, b = (int(x.strip()) for x in out.strip().splitlines()[0].split(","))
            return a, b
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return None

    def run(self) -> None:
        while not self._stop_evt.is_set():
            q = self.query()
            if q:
                self.vram.append(q[0])
                self.util.append(q[1])
            if self._ps:
                self.cpu.append(self._ps.cpu_percent(None))
            self._stop_evt.wait(self.interval)

    def stop(self, baseline_mib: int) -> dict:
        self._stop_evt.set()
        self.join(timeout=5)
        out = {"nvidia_vram_baseline_mib": baseline_mib}
        if self.vram:
            out.update(nvidia_vram_peak_mib=max(self.vram), nvidia_vram_delta_mib=max(self.vram) - baseline_mib,
                       nvidia_util_avg_pct=round(sum(self.util) / len(self.util), 1),
                       nvidia_util_peak_pct=max(self.util))
        if self.cpu:
            out.update(cpu_avg_pct=round(sum(self.cpu) / len(self.cpu), 1), cpu_peak_pct=round(max(self.cpu), 1))
        return out


def _gl_renderer(log: Path) -> str | None:
    try:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            if "GL_RENDERER=" in line:
                r = re.sub(r"\x1b\[[0-9;]*m", "", line.split("GL_RENDERER=", 1)[1])
                return r.split('", source:')[0].strip().rstrip('"')
    except OSError:
        pass
    return None


# ------------------------------------------------------------------ props y render

def layout_for(aspect: str, frames: int, fps: int) -> dict:
    """Frame size and reserved horizontal bands (nothing drawn there)."""
    from . import karaoke, theme_paper
    if aspect == "9:16":
        W, H = karaoke.W, karaoke.H
        half = round(karaoke.SIZE * 1.25)              # una línea de karaoke (110) con margen
        reserved = [[karaoke.CENTER_Y - half, karaoke.CENTER_Y + half],      # karaoke de Shorts (tercio medio)
                    [round(H * (1 - theme_paper.SUBTITLE_BAND)), H]]         # UI de Shorts abajo
    else:
        W, H = 1920, 1080
        reserved = [[theme_paper.scenes_theme()["frame"]["subtitle_top"], H]]  # 20 % inferior: subtítulos
    return {"aspect": aspect, "width": W, "height": H, "fps": fps, "frames": frames, "reserved": reserved}


def build_props(scene, fps: int, metrics: dict | None, gl_probe: bool = True) -> dict:
    from . import theme_paper
    return {
        "theme": theme_paper.scenes_theme(),
        "fonts": [{"family": f["family"], "weight": f["weight"], "src": f["src"]} for f in theme_paper.font_assets()],
        "metrics": metrics,
        "data": scene.data,
        "layout": layout_for(scene.aspect, scene.frames, fps),
        "scene3d": {"gl_probe": gl_probe, "supersample": 1},
    }


def render_scene3d(scene, cfg: dict, workdir: Path, cache_dir: Path, metrics: dict | None = None,
                   opts: dict | None = None) -> dict:
    """Render one 3D scene to a normalised clip (scene.clip). Mirrors explain.render_explain.

    scene: Scene3D-like (id, composition, frames, aspect, data). metrics: measured figures of the
    reference run (metrics.reference_metrics), injected as props so nothing is hard-coded in TSX."""
    from . import theme_paper
    from .explain import _normalize
    o = {**DEFAULTS, **cfg.get("scene3d", {}), **(opts or {})}
    fps = cfg["video"]["fps"]
    if scene.composition not in COMPOSITIONS:
        raise Scene3DFailed(f"unknown composition {scene.composition!r} (valid: {', '.join(COMPOSITIONS)})")
    props = build_props(scene, fps, metrics)
    bkey = bundle_key()
    key = hashlib.sha1(json.dumps([CACHE_VERSION, scene.composition, props, bkey, theme_paper.VERSION,
                                   theme_paper.look_hash(), o["jpeg_quality"]],
                                  ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    out = Path(cache_dir) / "scene3d" / "clips" / f"{scene.id}_{key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    rec = {"id": scene.id, "composition": scene.composition, "aspect": scene.aspect, "frames": scene.frames,
           "duration_s": round(scene.frames / fps, 3), "gl": o["gl"], "cached": out.exists(), "attempts": []}
    if out.exists():
        scene.clip = out
        rec.update(render_s=0.0, normalize_s=0.0, seconds=0.0)
        return rec
    t_all = time.perf_counter()
    deps = ensure_deps(cache_dir, o)
    bundle, bundle_s = ensure_bundle(deps, o)
    rec["bundle_s"] = bundle_s
    proj = Path(workdir) / "scene3d" / scene.id
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    raw = proj / "raw.mp4"
    cmd = cli(deps) + ["render", str(bundle), scene.composition, str(raw), f"--props={proj / 'props.json'}",
                       "--codec=h264", "--image-format=jpeg", f"--jpeg-quality={o['jpeg_quality']}",
                       f"--concurrency={o['concurrency']}", f"--browser-executable={browser_exe(deps)}",
                       "--log=verbose", "--overwrite"]
    for n in range(1, o["attempts"] + 1):
        raw.unlink(missing_ok=True)
        log = proj / f"render_{n}.log"
        gl = o["gl_fallback"] if (n == o["attempts"] and n > 1 and o.get("gl_fallback")) else o["gl"]
        base = _Sampler.query()
        sampler = _Sampler()
        sampler.start()
        t0 = time.perf_counter()
        try:
            _run(cmd + [f"--gl={gl}"], deps, o["timeout_s"], log)          # cwd = deps: ahí está node_modules/.remotion
            render_s = time.perf_counter() - t0
            usage = sampler.stop(base[0] if base else 0)
            t1 = time.perf_counter()
            _normalize(raw, out, scene.frames, fps)
            rec["attempts"].append({"n": n, "ok": True, "gl": gl, "seconds": round(time.perf_counter() - t0, 2)})
            rec.update(gl=gl, render_s=round(render_s, 2), normalize_s=round(time.perf_counter() - t1, 2),
                       seconds=round(time.perf_counter() - t_all, 2), gl_renderer=_gl_renderer(log),
                       fps_render=round(scene.frames / render_s, 2), log=str(log), **usage)
            scene.clip = out
            return rec
        except Exception as e:  # noqa: BLE001 — se registra y se reintenta
            sampler.stop(0)
            rec["attempts"].append({"n": n, "ok": False, "gl": gl, "seconds": round(time.perf_counter() - t0, 2),
                                    "error": f"{type(e).__name__}: {e}"[:500], "log": str(log)})
    err = Scene3DFailed(f"{scene.id} failed {o['attempts']} times: {rec['attempts'][-1]['error']}")
    err.rec = rec
    raise err


# ------------------------------------------------------------------ hojas de contacto

def frame_png(video: Path, t: float, dst: Path) -> Path:
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-ss", f"{t:.3f}", "-frames:v", "1",
                        str(dst)], capture_output=True, text=True, creationflags=_NOWIN)
    if p.returncode != 0 or not dst.exists():
        raise RuntimeError(f"frame grab failed at {t}s: {p.stderr[-300:]}")
    return dst


def probe_duration(video: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, creationflags=_NOWIN)
    return float(p.stdout.strip())


def contact_sheet(rows: list[tuple[str, Path]], times: list[float | str], dst: Path, thumb_w: int = 480) -> Path:
    """One row per video: frames at `times` (seconds, or "end"), labelled. Returns dst (PNG)."""
    from PIL import Image, ImageDraw, ImageFont

    from . import theme_paper
    p = theme_paper.palette()
    font = ImageFont.truetype(str(theme_paper.FONT_FILES["body_600"]), 22)
    small = ImageFont.truetype(str(theme_paper.FONT_FILES["mono_400"]), 18)
    tmp = dst.parent / f".{dst.stem}_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    grabbed = []
    for label, video in rows:
        dur = probe_duration(video)
        ims = []
        for i, t in enumerate(times):
            tt = max(0.0, dur - 1 / 30 - 0.001) if t == "end" else min(float(t), dur - 0.04)
            im = Image.open(frame_png(video, tt, tmp / f"{video.stem}_{i}.png")).convert("RGB")
            ims.append((tt, im))
        grabbed.append((label, ims))
    th = lambda im: (thumb_w, round(im.height * thumb_w / im.width))  # noqa: E731
    gap, head, cap = 16, 40, 30
    h_rows = [max(th(im)[1] for _, im in ims) for _, ims in grabbed]
    W = gap + len(times) * (thumb_w + gap)
    H = gap + sum(head + h + cap + gap for h in h_rows)
    sheet = Image.new("RGB", (W, H), p["card_bg"])
    d = ImageDraw.Draw(sheet)
    y = gap
    for (label, ims), hr in zip(grabbed, h_rows):
        d.text((gap, y + 6), label, font=font, fill=p["title"])
        y += head
        for i, (tt, im) in enumerate(ims):
            x = gap + i * (thumb_w + gap)
            sheet.paste(im.resize(th(im), Image.LANCZOS), (x, y))
            d.rectangle([x - 1, y - 1, x + th(im)[0], y + th(im)[1]], outline=p["card_border"])
            d.text((x, y + hr + 6), f"t = {tt:.2f} s", font=small, fill=p["muted"])
        y += hr + cap + gap
    sheet.save(dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return dst


# ------------------------------------------------------------------ demo

def _latest_2d(explain_id: str, cache_dir: Path) -> Path | None:
    """Newest cached explainroo clip of that scene (explain/ or explain.warm/ while produce runs cold)."""
    clips = [p for sub in ("explain", "explain.warm") for p in (Path(cache_dir) / sub).glob(f"{explain_id}_*.mp4")]
    clips.sort(key=lambda p: p.stat().st_mtime)
    return clips[-1] if clips else None


DEMOS = [
    # (escena 3D, id 2D equivalente en scripts/test_script.scenes.js)
    (Scene3D("GpuMemory3D", "GpuMemory3D", 180, data={"title": "Peak *GPU memory*", "value": 2.3, "max": 8}), "x26"),
    (Scene3D("Pipeline3D", "Pipeline3D", 180, data={"title": "Five agents, one *Producer*"}), "x05"),
    (Scene3D("Assembly3D", "Assembly3D", 180, data={"title": "*FFmpeg* stitches one file"}), "x17"),
    (Scene3D("GpuMemory3D_short", "GpuMemory3D", 180, aspect="9:16",
             data={"title": "Peak *GPU memory*", "value": 2.3, "max": 8}), None),
]


def demo(gl: str | None = None, only: list[str] | None = None, force: bool = False, bench: bool = False,
         extra: dict | None = None) -> list[dict]:
    """Render the demos. bench=True: only render and measure (nothing is written to runs/)."""
    from .config import load_config
    from .metrics import reference_metrics
    from .workspace import atomic_move
    cfg = load_config()
    cache = tmp_root() / "cache"
    work = tmp_root() / "scene3d_demo"
    final = PROJECT_ROOT / cfg["paths"]["runs"] / "scene3d_demo"
    final.mkdir(parents=True, exist_ok=True)
    metrics = reference_metrics(PROJECT_ROOT / "runs" / "2026-11-16_test" / "manifest.json")
    opts = {**({"gl": gl} if gl else {}), **(extra or {})}
    recs = []
    for scene, id2d in DEMOS:
        if only and scene.id not in only:
            continue
        if force:
            for f in (cache / "scene3d" / "clips").glob(f"{scene.id}_*.mp4"):
                f.unlink()
        try:
            rec = render_scene3d(scene, cfg, work, cache, metrics, opts)
        except Scene3DFailed as e:
            if not bench:
                raise
            rec = {**getattr(e, "rec", {}), "id": scene.id, "gl": opts.get("gl", DEFAULTS["gl"]), "failed": str(e)[:300]}
            print(json.dumps({"id": scene.id, "gl": rec["gl"], "failed": rec["failed"]}))
            recs.append(rec)
            continue
        print(json.dumps({k: rec.get(k) for k in ("id", "gl", "gl_renderer", "cached", "bundle_s", "render_s",
                                                    "normalize_s", "fps_render", "nvidia_vram_peak_mib",
                                                    "nvidia_vram_delta_mib", "nvidia_util_avg_pct", "cpu_avg_pct")}))
        rec["install"] = install_info(deps_dir(cache))
        recs.append(rec)
        if bench:
            continue
        tmp_mp4 = work / f"{scene.id}.mp4"
        shutil.copy2(scene.clip, tmp_mp4)
        atomic_move(tmp_mp4, final / tmp_mp4.name)
        sheet = contact_sheet([(f"3D · {scene.id} ({scene.aspect})", scene.clip)], [0, 0.3, 0.6, 3, "end"],
                              work / f"{scene.id}_sheet.png", thumb_w=480 if scene.aspect == "16:9" else 220)
        atomic_move(sheet, final / sheet.name)
        clip2d = _latest_2d(id2d, cache) if id2d else None
        if clip2d:
            cmp_png = contact_sheet([(f"2D · explainroo {id2d} (cached clip {clip2d.name})", clip2d),
                                     (f"3D · Remotion {scene.id}", scene.clip)], [0, 0.3, 0.6, 3, "end"],
                                    work / f"{scene.id}_vs_2d_{id2d}.png")
            atomic_move(cmp_png, final / cmp_png.name)
    return recs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="3D scene prototype (Remotion + Three.js)")
    ap.add_argument("cmd", choices=["demo", "install"])
    ap.add_argument("--gl", default=None, help="angle | egl | swangle | swiftshader | vulkan | angle-egl")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true", help="ignore the clip cache")
    ap.add_argument("--bench", action="store_true", help="render and measure only; write nothing to runs/")
    ap.add_argument("--attempts", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=None, help="seconds per attempt")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--out", default=None, help="write the records as JSON here")
    a = ap.parse_args()
    if a.cmd == "install":
        d = ensure_deps(tmp_root() / "cache")
        print(json.dumps({"deps": str(d), **install_info(d)}, indent=1))
    else:
        extra = {k: v for k, v in (("attempts", a.attempts), ("timeout_s", a.timeout), ("concurrency", a.concurrency)) if v}
        r = demo(a.gl, a.only, a.force, a.bench, extra)
        if a.out:
            Path(a.out).write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")

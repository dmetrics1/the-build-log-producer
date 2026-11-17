"""EXPLAIN scenes rendered with explainroo (Node, CPU + headless Chromium).

Used only as an animation engine: each scene is a one-scene project with no
narration that lasts exactly as long as our voice (min = frames / fps); no music,
effects or watermark. The drawing functions live in scripts/<script>.scenes.js.

Known cause (2026-11-16): if the process cannot see ffmpeg in PATH, `explainroo render`
does not fail, it hangs (it swallows the encoder error). That is why here:
  - PATH is already completed from the registry (config.py),
  - EXPLAINROO_FFMPEG / EXPLAINROO_FFPROBE are passed as absolute paths,
  - every attempt has a timeout (90 s) and counts as a failure; 3 failures stop the run.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

VIDEO_JSON = {
    "title": "scene", "theme": "look.json", "size": "16:9", "music": False, "sfx": False,
    "watermark": False, "captions": False, "transition": "cut", "camera": "still",
    "lead": 0, "hold": 0, "end": 0, "defaults": "0.6",
}
# tema visual: look.json + fuentes + marca + efectos (theme_paper.explainroo_video) y `const THEME`
# antepuesto a scenes.js (theme_paper.scenes_theme). sfx False: solo suenan nuestros s.sound().


def video_json(fps: int) -> dict:
    from . import theme_paper
    return {**VIDEO_JSON, **theme_paper.explainroo_video(), "fps": fps}


def write_project(proj: Path, data: dict, script_md: str, scenes_js: str, metrics: dict | None, fps: int) -> None:
    """Write a complete explainroo project: video.json, look.json, assets (fonts, effects),
    script.md and scenes.js with `const SCENES`, `const METRICS` and `const THEME` prepended."""
    from . import theme_paper
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "video.json").write_text(json.dumps(video_json(fps)), encoding="utf-8")
    theme_paper.write_explainroo_assets(proj)
    (proj / "script.md").write_text(script_md, encoding="utf-8")
    (proj / "scenes.js").write_text(f"const SCENES = {json.dumps(data, ensure_ascii=False)};\n"
                                    f"const METRICS = {json.dumps(metrics, ensure_ascii=False)};\n"
                                    f"const THEME = {json.dumps(theme_paper.scenes_theme(), ensure_ascii=False)};\n"
                                    + scenes_js, encoding="utf-8")


class ExplainFailed(RuntimeError):
    pass


def explainroo_cmd(package: str) -> list[str]:
    """Use the package npx already downloaded (saves ~1.5 s of npx per scene)."""
    version = package.split("@")[-1]
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "npm-cache" / "_npx"
    for pj in sorted(base.glob("*/node_modules/explainroo/package.json")):
        try:
            if json.loads(pj.read_text(encoding="utf-8")).get("version") == version:
                return [shutil.which("node") or "node", str(pj.parent / "bin" / "explainroo.js")]
        except (OSError, json.JSONDecodeError):
            continue
    return [shutil.which("npx") or "npx", "--yes", package]


def explainroo_env() -> dict:
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ff or not fp:
        raise ExplainFailed("ffmpeg/ffprobe are not in PATH or in the registry; explainroo would hang")
    return {**os.environ, "EXPLAINROO_FFMPEG": ff, "EXPLAINROO_FFPROBE": fp,
            "ONNXRUNTIME_NODE_INSTALL_CUDA": "skip"}


def _run(cmd: list[str], cwd: Path, env: dict, timeout: float, log: Path) -> None:
    with open(log, "w", encoding="utf-8", errors="replace") as lf:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, creationflags=_NOWIN)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, creationflags=_NOWIN)
            p.wait(timeout=15)
            raise TimeoutError(f"explainroo exceeded {timeout:.0f} s (process killed)")
    if code != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
        raise ExplainFailed(f"explainroo exited with code {code}: {' | '.join(tail)}")


def _normalize(src: Path, dst: Path, frames: int, fps: int) -> None:
    """Fix fps and the exact frame count (clone the last frame if any are missing) and keep
    explainroo's audio (the s.sound() effects) as 48 kHz stereo with exactly the clip duration
    (padded with silence or trimmed); if explainroo delivered no audio, use silence."""
    from .assemble import (AUDIO_SR, CLIP_AUDIO_ARGS, COLOR_ARGS, COLOR_VF, clip_audio_filter, clip_samples,
                           has_audio)
    tmp = dst.with_name(dst.stem + ".writing.mp4")
    silence = [] if has_audio(src) else ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_SR}:cl=stereo"]
    # explainroo entrega yuvj420p (rango completo, bt470bg): se pasa a rango limitado bt709
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), *silence,
                        "-map", "0:v:0", "-map", "1:a:0" if silence else "0:a:0",
                        "-vf", f"fps={fps},tpad=stop_mode=clone:stop_duration=2,{COLOR_VF}",
                        "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                        *COLOR_ARGS, "-r", str(fps), "-af", clip_audio_filter(clip_samples(frames, fps)),
                        *CLIP_AUDIO_ARGS, str(tmp)], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=_NOWIN)
    if p.returncode != 0:
        raise RuntimeError(f"normalizing {src.name} failed: {p.stderr.strip()[-400:]}")
    os.replace(tmp, dst)


def render_explain(scene, scenes_js: str, cfg: dict, workdir: Path, cache_dir: Path,
                   metrics: dict | None = None) -> dict:
    """metrics: measured figures from the reference run (pipeline.reference_metrics), injected
    as `const METRICS` so diagrams carry no hard-coded numbers. None if there is no reference yet."""
    fps = cfg["video"]["fps"]
    ex = cfg["explain"]
    timeout, attempts = ex.get("timeout_s", 90), ex.get("attempts", 3)
    data = {scene.explain_id: {"label": scene.label, "text": scene.display_text,
                               "keywords": scene.keywords, "braces": scene.braces}}
    from . import theme_paper
    vjson = video_json(fps)
    key = hashlib.sha1(json.dumps([scenes_js, data, scene.frames, vjson, ex["package"], "color-v2", "audio-v1",
                                   ex.get("workers"), metrics, theme_paper.VERSION, theme_paper.look_hash()],
                                  ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    out = cache_dir / "explain" / f"{scene.explain_id}_{key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    rec = {"id": scene.explain_id, "scene": scene.index, "label": scene.label, "frames": scene.frames,
           "duration_s": round(scene.frames / fps, 3), "cached": out.exists(), "attempts": []}
    if out.exists():
        scene.clip = out
        rec.update(render_s=0.0, normalize_s=0.0, seconds=0.0)
        return rec
    proj = workdir / "explain" / scene.explain_id
    cmd = explainroo_cmd(ex["package"]) + ["render", "."]
    if ex.get("workers"):
        cmd += ["--workers", str(ex["workers"])]   # páginas de Chromium por escena
    env = explainroo_env()
    for n in range(1, attempts + 1):
        shutil.rmtree(proj, ignore_errors=True)
        write_project(proj, data,
                      f"# {scene.explain_id}\n\n## {scene.explain_id} {{min={scene.frames / fps:.3f} lead=0 hold=0}}\n",
                      scenes_js, metrics, fps)
        t0 = time.perf_counter()
        try:
            _run(cmd, proj, env, timeout, proj / "render.log")
            render_s = time.perf_counter() - t0
            t1 = time.perf_counter()
            _normalize(proj / "out" / "video.mp4", out, scene.frames, fps)
            rec["attempts"].append({"n": n, "ok": True, "seconds": round(time.perf_counter() - t0, 2)})
            rec.update(render_s=round(render_s, 2), normalize_s=round(time.perf_counter() - t1, 2),
                       seconds=round(time.perf_counter() - t0, 2))
            scene.clip = out
            return rec
        except Exception as e:  # noqa: BLE001 — se registra y se reintenta
            rec["attempts"].append({"n": n, "ok": False, "seconds": round(time.perf_counter() - t0, 2),
                                    "error": f"{type(e).__name__}: {e}"[:400], "log": str(proj / "render.log")})
    err = ExplainFailed(f"{scene.explain_id} failed {attempts} times: {rec['attempts'][-1]['error']}")
    err.rec = rec
    raise err

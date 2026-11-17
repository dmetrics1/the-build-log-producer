"""Automatic hook: the opening scene shows real shots of the video's own result.

Script tags:
  [SCREEN: ... | hook | in=0.5 | speed=2.8]   the hook scene (in = seconds skipped at the start of the
                                              source; speed = playback speed; without speed it is fitted
                                              to the scene, up to video.max_speed)
  [EXPLAIN: ... | hook_source]                 scenes whose rendered shots feed the hook (e.g. the verdict)
If no scene is tagged hook_source, the first EXPLAIN with `| metrics=...` (the main figure) is used,
or else the first EXPLAIN. The manifest records where the hook came from.
"""
from __future__ import annotations

import copy
import subprocess
from pathlib import Path

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def hook_scene(scenes: list):
    return next((s for s in scenes if s.params.get("hook") and s.frames > 0), None)


def hook_sources(scenes: list) -> tuple[list, str]:
    tagged = [s for s in scenes if s.params.get("hook_source") and s.frames > 0]
    if tagged:
        return tagged, "tagged hook_source scenes"
    explain = [s for s in scenes if s.kind == "EXPLAIN" and s.frames > 0]
    with_metric = [s for s in explain if s.params.get("metrics")]
    if with_metric:
        return with_metric[:1], "fallback: first EXPLAIN with the main figure (metrics=)"
    return explain[:1], "fallback: first EXPLAIN scene"


def render_hook(scene, sources: list, origin: str, cfg: dict, workdir: Path, cache_dir: Path) -> dict:
    """Concatenates the source shots (video only), then renders the hook scene from them with the
    SCREEN-recording stage (trim, speed, panel layout, color normalization)."""
    from . import assemble
    if not sources or any(s.clip is None for s in sources):
        raise RuntimeError("hook: the source scenes have no rendered clip yet")
    lst = workdir / "hook_sources.txt"
    lst.write_text("".join(f"file '{Path(s.clip).as_posix()}'\n" for s in sources), encoding="utf-8")
    src = workdir / "hook_source.mp4"
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-map", "0:v:0", "-c", "copy", str(src)], capture_output=True, text=True, creationflags=_NOWIN)
    if p.returncode != 0:
        raise RuntimeError(f"hook: concat failed: {p.stderr.strip()[-300:]}")
    fps = cfg["video"]["fps"]
    seg_total = sum(s.frames for s in sources) / fps
    target = scene.frames / fps
    t_in = float(scene.params.get("in", 0) or 0)
    speed = scene.params.get("speed")
    warnings = []
    if speed not in (None, True, "", "fit"):
        speed = float(speed)
        t_out = t_in + target * speed
        if t_out > seg_total:
            warnings.append(f"hook: speed {speed:g}x needs {t_out - t_in:.1f} s of source but only "
                            f"{seg_total - t_in:.1f} s exist; the last frame is held")
            t_out = seg_total
    else:
        t_out = seg_total
    stand_in = copy.copy(scene)
    stand_in.params = {"src": str(src), "in": f"{t_in:.3f}", "out": f"{t_out:.3f}"}
    rec = assemble.render_recording(stand_in, cfg, cache_dir)
    scene.clip = stand_in.clip
    return {"scene": scene.index, "origin": origin,
            "source_scenes": [{"scene": s.index, "explain_id": s.explain_id, "label": s.label,
                               "duration_s": round(s.frames / fps, 3)} for s in sources],
            "source_s": round(seg_total, 3), "in_s": t_in, "out_s": round(t_out, 3),
            "speed": rec.get("speed"), "scene_s": round(target, 3),
            "warnings": warnings + rec.get("warnings", []), "seconds": rec.get("seconds")}

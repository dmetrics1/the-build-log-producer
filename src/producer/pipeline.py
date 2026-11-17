"""Runs one Producer pass: script -> final.mp4 + final.srt + manifest.json.

Stages (each one timed in the manifest, with peak VRAM, CPU and RAM):
parse -> tts -> timeline -> align -> screens -> explain -> hook -> music -> subtitles -> assemble -> verify
(subtitles: final.srt with the full transcript + subs.ass with the callouts burned in over SCREEN scenes)
Intermediate files in %LOCALAPPDATA%\\tbl-tmp\\<run_id>; content cache in tbl-tmp\\cache
(it survives between runs: producing again only rebuilds what changed).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import __version__
from .config import PROJECT_ROOT, load_config, runs_root, tmp_root
from .manifest import Manifest, StageFailed, sha256_file
from .workspace import RunWorkspace

KNOWN_ISSUES = [{
    "id": "explainroo-hangs-without-ffmpeg-in-path",
    "found": "2026-11-16",
    "symptom": "explainroo render hangs after 'soundtrack: ... mixed' and writes no frames; still works",
    "cause": ("the terminal was opened before FFmpeg was installed (stale PATH) and explainroo swallows the "
              "encoder error (src/render.js: norm.catch(() => {})) instead of failing"),
    "confirmed": "same scene in PowerShell with the PATH from the registry: rendered in 4.9 s",
    "mitigation": ("config.py completes PATH from the registry; explain.py passes absolute "
                   "EXPLAINROO_FFMPEG/FFPROBE and stops each attempt at 90 s (counts as a failure, max 3)"),
}]


def _parallel(fn, items: list, workers: int) -> list:
    """Runs fn(item) on `workers` threads (each starts its own ffmpeg or node process), keeping order.
    If an item fails, cancels what is pending, records its attempts and re-raises."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results: dict[int, dict] = {}
    err = None
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(fn, it): k for k, it in enumerate(items)}
        for f in as_completed(futs):
            k = futs[f]
            try:
                results[k] = f.result()
            except Exception as e:  # noqa: BLE001
                results[k] = getattr(e, "rec", {"error": f"{type(e).__name__}: {e}"})
                if err is None:
                    err = e
                    pool.shutdown(wait=False, cancel_futures=True)
    ordered = [results[k] for k in sorted(results)]
    if err is not None:
        raise err
    return ordered


def _load_previous(ws: RunWorkspace, filename: str = "manifest.json") -> list:
    mf = ws.final_dir / filename
    if not mf.exists():
        return []
    old = json.loads(mf.read_text(encoding="utf-8"))
    prev = old.get("previous_passes", [])
    prev.append({k: old.get(k) for k in ("pass", "variant", "created_at", "finished_at", "status", "total_seconds",
                                         "outputs", "costs", "summary", "approved", "approval")}
                | {"stages": [{"name": s["name"], "seconds": s.get("seconds"), "status": s.get("status"),
                               "vram_peak_mib": s.get("vram_peak_mib"),
                               # frases y desfasadas: las usa {{phrases}} / {{flagged}} (metrics.FIGURES)
                               **({"check": {k: (s.get("check") or {}).get(k) for k in ("phrases", "flagged")}}
                                  if s["name"] == "subtitles" else {})}
                              for s in old.get("stages", [])]})
    return prev


def produce(script: Path, slug: str | None = None, variant: str | None = None) -> Path:
    from . import align, assemble, explain, metrics, scenes as sc_mod, tts

    t_start = time.perf_counter()
    cfg = load_config()
    sfx = ""
    if variant:
        vv = cfg.get("variants", {}).get(variant)
        if vv is None:
            raise SystemExit(f"unknown variant: {variant} (config.toml [variants.*])")
        if "voice_speed" in vv:
            cfg["voice"]["speed"] = vv["voice_speed"]
        if "scene_gap_s" in vv:
            cfg.setdefault("timeline", {})["scene_gap_s"] = vv["scene_gap_s"]
        sfx = f"_{variant}"
    script = Path(script).resolve()
    slug = slug or sc_mod.read_meta(script).get("slug") or script.stem
    ws = RunWorkspace(slug, cfg)
    # cifras medidas que muestran los diagramas y dice la voz ({{ }}): última pasada en frío de la versión
    # principal de ESTE run; si aún no tiene, la más reciente de cualquier run
    ref_metrics, ref_src = metrics.reference_metrics(ws.final_dir / "manifest.json"), ws.final_dir.name
    if ref_metrics is None:
        ref_metrics, ref_src = metrics.latest_cold_reference(runs_root(cfg))
    figures = metrics.figure_units(ref_metrics)
    meta, scenes = sc_mod.parse_script(script, figures=figures)
    m = Manifest(ws, cfg, slug, filename=f"manifest{sfx}.json")
    m.data["variant"] = variant or "main"
    m.data["previous_passes"] = _load_previous(ws, f"manifest{sfx}.json")
    m.data["reference_metrics"] = ref_metrics
    m.data["reference_metrics_run"] = ref_src if ref_metrics else None
    m.data["figures"] = figures
    m.data["pass"] = len(m.data["previous_passes"]) + 1
    m.data["producer_version"] = __version__
    m.data["known_issues"] = KNOWN_ISSUES
    cache = tmp_root() / "cache"
    fps = cfg["video"]["fps"]
    scenes_js_path = script.with_suffix(".scenes.js")
    v = cfg["voice"]

    rel = lambda p: str(p.relative_to(PROJECT_ROOT)) if p.is_relative_to(PROJECT_ROOT) else str(p)  # noqa: E731
    m.data["inputs"] = {"script": rel(script), "script_sha256": sha256_file(script),
                        "scenes_js": rel(scenes_js_path) if scenes_js_path.exists() else None,
                        "scenes_js_sha256": sha256_file(scenes_js_path) if scenes_js_path.exists() else None,
                        "meta": meta}
    m.data["voice"] = {"engine": "kokoro", "model": v["model"], "voice": v["voice"], "speed": v["speed"],
                       "lang_code": v["lang_code"], "sample_rate": v["sample_rate"]}
    m.data["seeds"] = {"kokoro": "n/a (inferencia determinista)", "whisper": "n/a (beam search, temperatura 0)",
                       "explainroo": "n/a (s.rand determinista)", "music": "n/a (senoidales)"}
    m.data["prompts"] = [{
        "artifact": "scripts/test_script.md + scripts/test_script.scenes.js",
        "author": "LLM-assisted draft",
        "prompt": "Plan phases 3/4: 3-minute script 'How this video pipeline works' following the channel's script template",
        "api_cost_usd": 0.0, "note": "sin llamadas a la Claude API desde el pipeline",
    }]
    m.save()

    # 1. parse
    disclosure_cfg: dict = {}

    def st_parse(rec):
        from . import affiliates
        aff = affiliates.load()
        disclosure_cfg.update(aff["disclosure"])
        rec["warnings"] = [f"the script asks for {k}={meta[k]!r} but {k}={v[k]!r} from config.toml is used"
                           for k in ("voice", "speed") if k in meta and meta[k] != v[k]
                           and not (variant and k == "speed")]   # la variante cambia la velocidad a propósito
        for w in rec["warnings"]:
            print(f"WARNING {w}")
        full_text = " ".join(f"{s.spoken_text} {s.display_text}" for s in scenes)
        programs = affiliates.mentioned(full_text, aff)
        rec["disclosure"] = sc_mod.apply_affiliate_disclosure(meta, scenes, programs, aff["disclosure"])
        # para el Publicador: enlaces y bloque de descripción de este video
        m.data["affiliates"] = {"mentioned": [p["id"] for p in programs],
                                "links": {p["id"]: p["url"] for p in programs},
                                "rules": {p["id"]: p.get("rules") for p in programs},
                                "description_block": affiliates.description_block(programs, aff)}
        rec.update(scenes=len(scenes), screen=sum(s.kind == "SCREEN" for s in scenes),
                   explain=sum(s.kind == "EXPLAIN" for s in scenes),
                   words_spoken=sum(len(s.spoken_text.split()) for s in scenes))
    m.run_stage("parse", st_parse, attempts=1)

    # 2. tts
    def st_tts(rec):
        rec.update(tts.synthesize(scenes, cfg, cache))
    m.run_stage("tts", st_tts)
    m.data["models"]["tts"] = {"name": v["model"], "voice": v["voice"], "device": "cuda"}

    # 3. timeline + narración completa
    narration = ws.tmp("narration.wav")

    def st_timeline(rec):
        rec.update(tts.build_timeline(scenes, cfg, narration))
        min_s = cfg["video"].get("min_scene_s", 2.5)
        rec["min_scene_s"] = min_s
        rec["merged_shots"] = sc_mod.plan_shots(scenes, fps, min_s)
        rec["scenes_changed"] = sum(len(g["scenes"]) for g in rec["merged_shots"])
        rec["shots"] = sum(1 for s in scenes if s.frames > 0)
    m.run_stage("timeline", st_timeline, attempts=1)

    # 4. align
    def st_align(rec):
        if cfg["align"].get("mode", "full") == "full":
            rec.update(align.align_full(scenes, cfg, cache, narration))
        else:
            rec.update(align.align_scenes(scenes, cfg, cache))
        rec["energy_refine"] = align.refine_with_energy(scenes, narration)
        rec["non_whisper_words"] = align.non_whisper_words(scenes)      # con los tiempos finales
        # divulgación de afiliados: la FRASE debe empezar antes de max_start_s (regla del canal: primeros 30 s)
        disc = m.data["stages"][0].get("disclosure", {})
        if disc.get("inserted"):
            s = next(x for x in scenes if x.index == disc["scene"])
            start = s.audio_offset + s.units[disc["first_unit"]].start
            limit = float(disclosure_cfg.get("max_start_s", 30))
            rec["disclosure_start_s"] = round(start, 2)
            if start > limit:
                raise RuntimeError(f"the affiliate disclosure starts at {start:.1f} s (limit {limit:g} s): "
                                   f"move it earlier in the script")
    m.run_stage("align", st_align)
    m.data["models"]["align"] = {"name": f"faster-whisper {cfg['align']['model']}",
                                 "compute_type": cfg["align"]["compute_type"], "device": cfg["align"]["device"]}

    # 5. screens
    def st_screens(rec):
        todo = [s for s in scenes if s.kind == "SCREEN" and s.frames > 0 and not s.params.get("hook")]
        rec["parallel"] = cfg["video"].get("screen_parallel", 1)
        rec["scenes"] = _parallel(lambda s: assemble.render_screen_scene(s, cfg, cache), todo, rec["parallel"])
        rec["recordings"] = sum(1 for s in todo if s.params.get("src"))
        rec["warnings"] = [f"escena {r['scene']}: {w}" for r in rec["scenes"] for w in r.get("warnings", [])]
        for w in rec["warnings"]:
            print(f"WARNING {w}")
        rec["absorbed"] = [s.index for s in scenes if s.kind == "SCREEN" and s.frames == 0]
    m.run_stage("screens", st_screens)

    # 6. explain (reintentos por escena dentro de explain.py: 3 intentos de 90 s)
    scenes_js = scenes_js_path.read_text(encoding="utf-8")

    def st_explain(rec):
        rec["scenes"] = []
        rec["package"] = cfg["explain"]["package"]
        rec["command"] = " ".join(explain.explainroo_cmd(cfg["explain"]["package"])[:1]) + " explainroo.js render"
        rec["absorbed"] = [s.explain_id for s in scenes if s.kind == "EXPLAIN" and s.frames == 0]
        rec["parallel"] = cfg["explain"].get("parallel", 1)
        rec["workers_per_scene"] = cfg["explain"].get("workers") or "default (8)"
        todo = [s for s in scenes if s.kind == "EXPLAIN" and s.frames > 0 and not s.params.get("scene3d")]
        todo3d = [s for s in scenes if s.kind == "EXPLAIN" and s.frames > 0 and s.params.get("scene3d")]
        rec["scenes"] = _parallel(lambda s: explain.render_explain(s, scenes_js, cfg, ws.tmp_dir, cache, ref_metrics),
                                  todo, rec["parallel"])
        if todo3d:
            # | scene3d=Comp : la escena EXPLAIN se renderiza en 3D (Remotion + Three.js en la GPU), en serie:
            # cada render ya usa varias pestañas de Chrome y la CPU es el cuello de botella
            from . import scene3d as s3d

            def render3d(s):
                sc = s3d.Scene3D(id=s.explain_id, composition=str(s.params["scene3d"]), frames=s.frames, index=s.index)
                r = s3d.render_scene3d(sc, cfg, ws.tmp_dir, cache, ref_metrics)
                s.clip = sc.clip
                return {"scene": s.index, "renderer": "scene3d", **r}
            rec["scenes3d"] = _parallel(render3d, todo3d, 1)
    m.run_stage("explain", st_explain, attempts=1)

    # 6b. hook: the opening scene is built from the rendered shots of the hook_source scenes
    from . import hook as hook_mod
    hsc = hook_mod.hook_scene(scenes)
    if hsc is not None:
        def st_hook(rec):
            sources, origin = hook_mod.hook_sources(scenes)
            rec.update(hook_mod.render_hook(hsc, sources, origin, cfg, ws.tmp_dir, cache))
            for w in rec["warnings"]:
                print(f"WARNING {w}")
            m.data["hook"] = {k: rec[k] for k in ("scene", "origin", "source_scenes", "source_s", "in_s",
                                                  "out_s", "speed", "scene_s", "warnings")}
        m.run_stage("hook", st_hook)
    else:
        m.data["hook"] = None
    m.data["models"]["explain"] = {"name": cfg["explain"]["package"], "theme": "midnight", "renderer": "Chromium headless (CPU)"}

    # 7. music
    music_holder: dict = {}

    def st_music(rec):
        total_s = sum(s.frames for s in scenes) / fps
        path, info = assemble.make_music(cfg, total_s, ws.tmp_dir, meta.get("music"))
        music_holder["path"] = path
        rec.update(info)
    m.run_stage("music", st_music)

    # 8. subtitles
    ass, srt, check_md = ws.tmp("subs.ass"), ws.tmp(f"final{sfx}.srt"), ws.tmp(f"subtitle_check{sfx}.md")

    def st_subs(rec):
        # final.srt = transcripción completa (closed captions); subs.ass = solo callouts sobre SCREEN
        info, phrases = assemble.build_subtitles(scenes, cfg, ass, srt)
        rec.update(info)
        rec["check"] = assemble.subtitle_report(phrases, scenes, narration, check_md, callouts=info["callouts"])
        for c in info["callouts"]:
            for f in c["flags"]:
                print(f"WARNING callout {c['phrase']} (scene {c['scene']}, {c['text']!r}): {f}")
        rows = metrics.check_script(scenes, ref_metrics)
        rec["metric_checks"] = rows
        rec["metric_warnings"] = sum(1 for r in rows if r["status"] != "ok")
        with open(check_md, "a", encoding="utf-8") as f:
            f.write(metrics.check_markdown(rows, ref_metrics))
        for r in rows:
            if r["status"] != "ok":
                print(f"WARNING figure in scene {r['scene']} ({r['metric']}): script {r['script']!r} vs manifest {r['manifest']!r} -> {r['status']}")
    m.run_stage("subtitles", st_subs)
    ws.publish(check_md, f"subtitle_check{sfx}.md")

    # 9. assemble -> final.mp4 (move atómico a runs/)
    final_tmp = ws.tmp(f"final{sfx}.mp4")

    def st_assemble(rec):
        rec.update(assemble.assemble(scenes, narration, music_holder["path"], ass, cfg, ws.tmp_dir, final_tmp))
        rec["ffmpeg"] = assemble.ffmpeg_version()
    m.run_stage("assemble", st_assemble)
    final = ws.publish(final_tmp, f"final{sfx}.mp4")
    ws.publish(srt, f"final{sfx}.srt")

    # 10. verify
    def st_verify(rec):
        p = assemble.probe(final)
        rec.update(p)
        v_ = cfg["video"]
        if (p["width"], p["height"], p["fps"]) != (v_["width"], v_["height"], f"{v_['fps']}/1"):
            raise RuntimeError(f"unexpected output: {p['video']}")
        rec["content"] = assemble.content_scan(final)
        for w in rec["content"]["near_empty_warnings"]:
            print(f"WARNING near-empty picture from {w['from_s']} s to {w['to_s']} s (min content {w['min_content_pct']} %)")
    m.run_stage("verify", st_verify, attempts=1)

    # resumen, costos
    stages = {s["name"]: s for s in m.data["stages"]}
    total_s = round(sum(s["seconds"] for s in m.data["stages"]), 2)
    c = cfg["costs"]
    kwh = c["laptop_watts"] * total_s / 3600 / 1000
    ex_scenes = stages["explain"]["scenes"]
    ex_render = round(sum(x.get("seconds", 0) for x in ex_scenes), 2)
    m.data["outputs"] = {"final_mp4": f"final{sfx}.mp4", "subtitles_srt": f"final{sfx}.srt",
                         "subtitle_check": f"subtitle_check{sfx}.md",
                         **{k: stages["verify"][k] for k in ("duration_s", "size_mb", "video", "audio")}}
    m.data["costs"] = {
        "software_usd": 0.0, "claude_api_usd": 0.0,
        "electricity_kwh": round(kwh, 5), "electricity_usd": round(kwh * c["kwh_price_usd"], 4),
        "formula": f"{c['laptop_watts']} W × {total_s} s ÷ 3600 ÷ 1000 × USD {c['kwh_price_usd']}/kWh",
        "total_usd": round(kwh * c["kwh_price_usd"], 4),
    }
    m.data["summary"] = {
        "total_seconds": total_s,
        "wall_seconds": round(time.perf_counter() - t_start, 2),
        "script_to_mp4": "wall_seconds: from reading the script to a verified final.mp4",
        "vram_peak_mib": max(s.get("vram_peak_mib", 0) for s in m.data["stages"]),
        "slowest_stages": sorted(({"name": s["name"], "seconds": s["seconds"]} for s in m.data["stages"]),
                                 key=lambda x: -x["seconds"])[:3],
        "explain": {"scenes": len(ex_scenes), "rendered": sum(not x.get("cached") for x in ex_scenes),
                    "parallel": stages["explain"].get("parallel"),
                    "sum_of_scene_s": ex_render, "stage_wall_s": stages["explain"]["seconds"],
                    "share_of_total": round(stages["explain"]["seconds"] / total_s, 3) if total_s else None,
                    "mean_s": round(ex_render / max(1, sum(not x.get("cached") for x in ex_scenes)), 2),
                    "slowest": sorted(ex_scenes, key=lambda x: -x.get("seconds", 0))[:3]},
        "music_placeholder": stages["music"].get("placeholder"),
        # en frío = nada de caché: toda la voz sintetizada, todas las EXPLAIN renderizadas, Whisper corrido
        "cold": (stages["tts"].get("synthesized") == len(scenes)
                 and all(not x.get("cached") for x in ex_scenes)
                 and stages["align"].get("whisper_calls", 1) == 1),
        "voice_speed": cfg["voice"]["speed"], "scene_gap_s": stages["timeline"].get("scene_gap_s"),
    }
    m.finish()
    # Fase 6: mensaje de aprobación por Telegram (solo si hay claves); nunca hace fallar la producción.
    # El resultado queda en el manifiesto como telegram_notification.
    try:
        from telegram_bot.notify import notify_if_configured
        notify_if_configured(final.parent, variant)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING telegram notification skipped: {type(e).__name__}")
    return final


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m producer produce <script.md> [--slug SLUG] [--variant NAME]")
        return 2
    slug = argv[argv.index("--slug") + 1] if "--slug" in argv else None
    variant = argv[argv.index("--variant") + 1] if "--variant" in argv else None
    t0 = time.perf_counter()
    try:
        final = produce(Path(argv[0]), slug, variant)
    except StageFailed as e:
        print(f"\nSTOPPED: {e}\nIntermediate files stay in the temp folder for diagnosis (see manifest.json).")
        return 1
    mf = json.loads((final.parent / (f"manifest_{variant}.json" if variant else "manifest.json")).read_text(encoding="utf-8"))
    s = mf["summary"]
    print(f"\nfinal.mp4: {final}\nduration: {mf['outputs']['duration_s']} s | total: {s['total_seconds']} s "
          f"| peak VRAM: {s['vram_peak_mib']} MiB | wall: {time.perf_counter() - t0:.1f} s")
    for st in mf["stages"]:
        print(f"  {st['name']:<10} {st['seconds']:>8.2f} s  VRAM {st.get('vram_peak_mib', 0):>5} MiB  {st['status']}")
    return 0

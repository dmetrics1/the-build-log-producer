"""Narration with Kokoro-82M, one track per scene (voice and speed from config.toml [voice]).

Content-addressed cache in <tmp>/cache/tts: the key is (spoken text, voice, speed, model).
Re-narrating only the lines that changed is automatic.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf


def _key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _trim(audio: np.ndarray, sr: int, thresh: float = 1e-3, keep_s: float = 0.04) -> np.ndarray:
    idx = np.flatnonzero(np.abs(audio) > thresh)
    if idx.size == 0:
        return audio
    keep = int(keep_s * sr)
    return audio[max(0, idx[0] - keep): min(len(audio), idx[-1] + keep)]


def synthesize(scenes: list, cfg: dict, cache_dir: Path) -> dict:
    v = cfg["voice"]
    sr = v["sample_rate"]
    out_dir = cache_dir / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    pipe, per_scene, load_s = None, [], 0.0
    for sc in scenes:
        key = _key(sc.spoken_text, v["voice"], v["speed"], v["model"], v["lang_code"])
        wav = out_dir / f"{key}.wav"
        cached = wav.exists()
        t0 = time.perf_counter()
        if not cached:
            if pipe is None:
                tl = time.perf_counter()
                from kokoro import KPipeline
                pipe = KPipeline(lang_code=v["lang_code"], device="cuda", repo_id=v["model"])
                load_s = time.perf_counter() - tl
                t0 = time.perf_counter()
            chunks = [a for _, _, a in pipe(sc.spoken_text, voice=v["voice"], speed=v["speed"])]
            audio = np.concatenate([c.detach().cpu().numpy() if hasattr(c, "detach") else np.asarray(c)
                                    for c in chunks]).astype(np.float32)
            audio = _trim(audio, sr)
            tmp = wav.with_name(wav.stem + ".writing.wav")
            sf.write(tmp, audio, sr)
            os.replace(tmp, wav)
        sc.audio_path = wav
        sc.audio_s = sf.info(str(wav)).frames / sr
        per_scene.append({"scene": sc.index, "cached": cached,
                          "seconds": round(time.perf_counter() - t0, 2), "audio_s": round(sc.audio_s, 2)})
    if pipe is not None:
        import torch
        del pipe
        torch.cuda.empty_cache()
    return {"model_load_s": round(load_s, 1), "scenes": per_scene,
            "synthesized": sum(1 for p in per_scene if not p["cached"]),
            "speech_s": round(sum(s.audio_s for s in scenes), 2)}


def build_timeline(scenes: list, cfg: dict, out_wav: Path, pad_in: float | None = None,
                   pad_out: float | None = None, tail: float | None = None) -> dict:
    """Assigns frames to each scene (voice + breathing room) and builds the full narration.
    config.toml [timeline]: scene_gap_s = silence between the end of one voice and the start of the next
    (pad_in before each voice + pad_out after), pad_in_s, tail_s at the end of the video."""
    fps, sr = cfg["video"]["fps"], cfg["voice"]["sample_rate"]
    tl = cfg.get("timeline", {})
    pad_in = tl.get("pad_in_s", 0.12) if pad_in is None else pad_in
    gap = tl.get("scene_gap_s", 0.30)
    pad_out = max(0.05, gap - pad_in) if pad_out is None else pad_out
    tail = tl.get("tail_s", 0.8) if tail is None else tail
    frame = 0
    for i, sc in enumerate(scenes):
        length = pad_in + sc.audio_s + pad_out + (tail if i == len(scenes) - 1 else 0)
        sc.frames = sc.narr_frames = max(1, round(length * fps))
        sc.start_frame = sc.narr_start_frame = frame
        sc.audio_offset = frame / fps + pad_in
        frame += sc.frames
    total_s = frame / fps
    track = np.zeros(int(round(total_s * sr)) + sr, dtype=np.float32)
    for sc in scenes:
        audio, _ = sf.read(str(sc.audio_path), dtype="float32")
        a = int(round(sc.audio_offset * sr))
        track[a:a + len(audio)] += audio
    track = track[: int(round(total_s * sr))]
    sf.write(str(out_wav), track, sr)
    return {"frames": frame, "duration_s": round(total_s, 3), "pad_in": pad_in, "pad_out": pad_out,
            "scene_gap_s": round(pad_in + pad_out, 3), "tail": tail}

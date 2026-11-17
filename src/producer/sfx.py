"""Sound effects (swoosh, tick, pop) placed on a clip's timeline.

Contract: each video clip may carry an audio track with ONLY its effects, at unity gain
(the final level, 18 dB below the voice, is applied at assembly: theme_paper.SFX). Renderers
call place() with their events [(seconds, name)] and the clip duration.
Files: assets/sfx/*.wav, 48 kHz stereo (generated, see assets/sfx/README.md).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from . import theme_paper

SR = 48000


def _load(name: str) -> np.ndarray:
    path = Path(theme_paper.SFX["files"][name])
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SR:
        raise ValueError(f"{path.name}: expected {SR} Hz, got {sr}")
    return audio if audio.shape[1] == 2 else np.repeat(audio[:, :1], 2, axis=1)


def place(events: list[tuple[float, str]], duration_s: float, out_wav: Path) -> Path:
    """Write a stereo WAV of `duration_s` with each effect at its time (trimmed at the end)."""
    n = int(round(duration_s * SR))
    track = np.zeros((n, 2), dtype=np.float32)
    cache: dict[str, np.ndarray] = {}
    for t, name in events:
        clip = cache.setdefault(name, _load(name))
        a = int(round(max(0.0, t) * SR))
        if a >= n:
            continue
        b = min(n, a + len(clip))
        track[a:b] += clip[: b - a]
    sf.write(str(out_wav), np.clip(track, -1, 1), SR, subtype="PCM_16")
    return Path(out_wav)

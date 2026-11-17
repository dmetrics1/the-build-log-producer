"""Per-word timestamps with faster-whisper large-v3-turbo.

Subtitle text comes from the script; only the timings are taken from Whisper
(matched word by word), because Whisper normalizes ("twelve" -> "12").
Import torch before faster_whisper: it provides cuBLAS/cuDNN to ctranslate2.
Per-audio cache in <tmp>/cache/align.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from pathlib import Path

import numpy as np


def _num_words(t: str) -> list[str]:
    try:
        from num2words import num2words
        return re.split(r"[\s-]+", num2words(float(t) if "." in t else int(t)).replace(",", ""))
    except Exception:  # noqa: BLE001
        return [t]


def norm_tokens(word: str) -> list[str]:
    w = re.sub(r"[^\w\s.'-]", " ", word.lower().replace("’", "'"))
    out = []
    for t in re.split(r"[\s-]+", w):
        t = t.strip(".'")
        if not t:
            continue
        out.extend(_num_words(t) if re.fullmatch(r"\d+(\.\d+)?", t) else [t])
    return out


SHOWN_WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’.\- ])*")   # letras (y ' . - espacio): sin cifras ni moneda


def shows_word(u) -> bool:
    """A Unit whose voice is only a PRONUNCIATION of what is shown: a dictionary word
    (config/pronounce.toml) or a {Kokoro|/phonemes/} / {Kokoro|koh-koh-roh} group whose visible
    word has no digits or currency. Whisper writes the real word, not the respelling."""
    return bool(getattr(u, "pron", False)) or (
        bool(getattr(u, "brace", False)) and SHOWN_WORD.fullmatch(u.value.strip()) is not None)


def unit_tokens(u) -> list[str]:
    """Tokens a Unit is matched with: what is shown if it is a pronunciation (shows_word);
    otherwise what is spoken ({$0|zero dollars}: Whisper hears "zero dollars")."""
    if shows_word(u):
        return norm_tokens(u.value)
    return [tok for sw in u.spoken for tok in norm_tokens(sw)]


def _join_split_names(W: list[tuple], targets: set[str], max_parts: int = 3) -> list[tuple]:
    """Whisper sometimes splits a name into several words ("Comfy UI", "Higgs field",
    "Explain Roo", "F. FMPEG"). Joins consecutive pieces whose concatenation is the visible
    token of a pronunciation Unit; the time runs from the start of the first to the end of the last."""
    if not targets:
        return W
    out, j = [], 0
    while j < len(W):
        for n in range(min(max_parts, len(W) - j), 1, -1):
            joined = "".join(t for t, _, _ in W[j:j + n])
            if joined in targets:
                out.append((joined, W[j][1], W[j + n - 1][2]))
                j += n
                break
        else:
            out.append(W[j])
            j += 1
    return out


def match_units(units: list, words: list[dict], audio_s: float) -> tuple[float, list[dict]]:
    """Assigns start/end to each Unit from Whisper's words.
    Returns (share of exact tokens, per-token report). Method of each token:
      whisper       Whisper heard that word: measured time
      replaced      Whisper heard another form ("8GB" for "eight gigabyte"): its span's time, split evenly
      interpolated  Whisper did not hear it: time interpolated between neighbors
    Pronunciation Units (shows_word) are matched against the visible word."""
    S = [(ui, tok) for ui, u in enumerate(units) for tok in unit_tokens(u)]
    W = []
    for w in words:
        toks = norm_tokens(w["w"]) or ["_"]
        step = (w["e"] - w["s"]) / len(toks)
        W += [(tok, w["s"] + k * step, w["s"] + (k + 1) * step) for k, tok in enumerate(toks)]
    W = _join_split_names(W, {tok for ui, tok in S if shows_word(units[ui])})
    times: list[list[float] | None] = [None] * len(S)
    method = ["interpolated"] * len(S)
    exact = 0
    sm = difflib.SequenceMatcher(None, [t for _, t in S], [t for t, _, _ in W], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = [W[j1 + k][1], W[j1 + k][2]]
                method[i1 + k] = "whisper"
            exact += i2 - i1
        elif op == "replace":
            a, b = W[j1][1], W[j2 - 1][2]
            step = (b - a) / (i2 - i1)
            heard = " ".join(t for t, _, _ in W[j1:j2])
            for k in range(i2 - i1):
                times[i1 + k] = [a + k * step, a + (k + 1) * step]
                method[i1 + k] = f"replaced (heard: {heard})"
    # interpola los que quedaron sin tiempo
    i = 0
    while i < len(times):
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None:
                j += 1
            a = times[i - 1][1] if i > 0 else 0.0
            b = times[j][0] if j < len(times) else audio_s
            step = max(0.0, b - a) / (j - i)
            for k in range(i, j):
                times[k] = [a + (k - i) * step, a + (k - i + 1) * step]
            i = j
        else:
            i += 1
    for ui, u in enumerate(units):
        ts = [times[k] for k, (uj, _) in enumerate(S) if uj == ui]
        if ts:
            u.start, u.end = min(t[0] for t in ts), max(t[1] for t in ts)
    report = [{"unit": ui, "word": units[ui].display, "spoken": tok, "start": round(times[k][0], 3),
               "end": round(times[k][1], 3), "method": method[k]} for k, (ui, tok) in enumerate(S)]
    return (round(exact / len(S), 3) if S else 1.0), report


def align_scenes(scenes: list, cfg: dict, cache_dir: Path) -> dict:
    a = cfg["align"]
    out_dir = cache_dir / "align"
    out_dir.mkdir(parents=True, exist_ok=True)
    model, load_s, per_scene = None, 0.0, []
    for sc in scenes:
        audio_hash = hashlib.sha1(Path(sc.audio_path).read_bytes()).hexdigest()[:16]
        jf = out_dir / f"{audio_hash}_{a['model']}.json"
        t0 = time.perf_counter()
        cached = jf.exists()
        if cached:
            words = json.loads(jf.read_text(encoding="utf-8"))
        else:
            if model is None:
                tl = time.perf_counter()
                import torch  # noqa: F401
                from faster_whisper import WhisperModel
                model = WhisperModel(a["model"], device=a["device"], compute_type=a["compute_type"])
                load_s = time.perf_counter() - tl
                t0 = time.perf_counter()
            segs, _ = model.transcribe(str(sc.audio_path), language="en", word_timestamps=True,
                                       beam_size=5, condition_on_previous_text=False, vad_filter=False)
            words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
                     for s in segs for w in (s.words or [])]
            jf.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        sc.align_ratio, sc.word_report = match_units(sc.units, words, sc.audio_s)
        per_scene.append({"scene": sc.index, "cached": cached, "seconds": round(time.perf_counter() - t0, 2),
                          "exact_match": sc.align_ratio, "whisper": " ".join(w["w"] for w in words)})
    if model is not None:
        import torch
        del model
        torch.cuda.empty_cache()
    ratios = [p["exact_match"] for p in per_scene]
    return {"model_load_s": round(load_s, 1), "scenes": per_scene,
            "exact_match_mean": round(sum(ratios) / len(ratios), 3),
            "worst": sorted(per_scene, key=lambda p: p["exact_match"])[:3],
            "non_whisper_words": non_whisper_words(scenes)}


def align_full(scenes: list, cfg: dict, cache_dir: Path, narration: Path) -> dict:
    """A single Whisper call over the full narration. Each word goes to the scene where it
    ends and is matched against that scene's script (match_units)."""
    a = cfg["align"]
    out_dir = cache_dir / "align"
    out_dir.mkdir(parents=True, exist_ok=True)
    jf = out_dir / f"full_{hashlib.sha1(Path(narration).read_bytes()).hexdigest()[:16]}_{a['model']}.json"
    load_s = transcribe_s = 0.0
    cached = jf.exists()
    if cached:
        words = json.loads(jf.read_text(encoding="utf-8"))
    else:
        tl = time.perf_counter()
        import torch  # noqa: F401
        from faster_whisper import WhisperModel
        model = WhisperModel(a["model"], device=a["device"], compute_type=a["compute_type"])
        load_s = time.perf_counter() - tl
        t0 = time.perf_counter()
        segs, _ = model.transcribe(str(narration), language="en", word_timestamps=True, beam_size=5,
                                   condition_on_previous_text=False, vad_filter=False)
        words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)}
                 for s in segs for w in (s.words or [])]
        transcribe_s = time.perf_counter() - t0
        jf.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        del model
        torch.cuda.empty_cache()
    per_scene = []
    # Frontera entre escenas = mitad del silencio entre la voz de una y la de la siguiente. Cada palabra
    # va a la escena donde TERMINA: Whisper adelanta el inicio de la primera palabra tras una pausa (se
    # "come" el silencio, más cuanto más largo es el hueco), pero su final es fiable.
    bounds = [-1e9] + [(scenes[k - 1].audio_offset + scenes[k - 1].audio_s + scenes[k].audio_offset) / 2
                       for k in range(1, len(scenes))] + [1e9]
    for i, sc in enumerate(scenes):
        lo, hi = bounds[i], bounds[i + 1]
        mine = [{"w": w["w"], "s": w["s"] - sc.audio_offset, "e": w["e"] - sc.audio_offset}
                for w in words if lo <= w["e"] - 0.02 < hi]
        sc.align_ratio, sc.word_report = match_units(sc.units, mine, sc.audio_s)
        clamp_to_scene_audio(sc)
        per_scene.append({"scene": sc.index, "exact_match": sc.align_ratio, "whisper": " ".join(w["w"] for w in mine)})
    ratios = [p["exact_match"] for p in per_scene]
    return {"mode": "full", "whisper_calls": 0 if cached else 1, "cached": cached,
            "model_load_s": round(load_s, 1), "transcribe_s": round(transcribe_s, 1), "words": len(words),
            "scenes": per_scene, "exact_match_mean": round(sum(ratios) / len(ratios), 3),
            "worst": sorted(per_scene, key=lambda p: p["exact_match"])[:3],
            "non_whisper_words": non_whisper_words(scenes)}


def clamp_to_scene_audio(sc) -> None:
    """Each scene's voice starts at its audio_offset (set by build_timeline) and lasts audio_s:
    no word can start before or end after that. Whisper moves the first word after a long silence
    up to ~0.8 s early (it "eats" the pause between scenes); this fixes it with an exact value."""
    lo, hi = 0.0, sc.audio_s
    for u in sc.units:
        if u.start is None:
            continue
        u.start = min(max(u.start, lo), hi - 0.05)
        u.end = min(max(u.end, u.start + 0.05), hi)


HOP_S, THR_DB, MIN_SIL_S, SNAP_MAX_S = 0.01, -40.0, 0.06, 0.4


def speech_mask(wav: Path) -> np.ndarray:
    """Speech/non-speech every 10 ms by energy (−40 dBFS threshold); silences < 60 ms count as speech."""
    import soundfile as sf
    audio, sr = sf.read(str(wav), dtype="float32")
    hop = int(sr * HOP_S)
    n = len(audio) // hop
    rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    speech = 20 * np.log10(rms) > THR_DB
    k = int(round(MIN_SIL_S / HOP_S))
    i = 0
    while i < n:                       # rellena pausas internas muy cortas
        if not speech[i]:
            j = i
            while j < n and not speech[j]:
                j += 1
            if j - i < k and i > 0 and j < n:
                speech[i:j] = True
            i = j
        else:
            i += 1
    return speech


def refine_with_energy(scenes: list, narration: Path) -> dict:
    """Whisper tends to start a word at the end of the previous pause (≈ −250 ms) and to
    end it before the voice fades out. Energy-based fix, word by word:
      - start inside a silence -> first frame with speech (max. 400 ms later);
      - end followed by speech that fades before the next word -> end of that speech (max. 400 ms).
    Only an edge that touches a real pause moves; inside a continuous phrase nothing changes."""
    sp = speech_mask(narration)
    n = len(sp)
    onsets = np.flatnonzero(sp[1:] & ~sp[:-1]) + 1          # silencio (≥ 60 ms) -> voz
    offsets = np.flatnonzero(sp[:-1] & ~sp[1:]) + 1         # voz -> silencio (≥ 60 ms)
    on_t, off_t = onsets * HOP_S, offsets * HOP_S
    idx = lambda t: min(n - 1, max(0, int(round(t / HOP_S))))  # noqa: E731
    moved_starts, moved_ends, adjustments = 0, 0, []

    def note(sc, u, edge, old, new):
        adjustments.append({"scene": sc.index, "word": u.display, "edge": edge, "ms": round((new - old) * 1000)})

    # 1) inicios
    for sc in scenes:
        for k, u in enumerate(sc.units):
            if u.start is None:
                continue
            g0, g1 = sc.audio_offset + u.start, sc.audio_offset + u.end
            prev = sc.units[k - 1] if k > 0 and sc.units[k - 1].start is not None else None
            prev_start = sc.audio_offset + prev.start if prev else sc.audio_offset - 1.0
            # Solo una palabra que sigue a una PAUSA DEL GUION (la anterior termina en puntuación, o es la
            # primera de la escena) puede tener su inicio en el arranque de voz tras un silencio: Kokoro
            # hace las pausas en la puntuación. Sin esto, la pausa DESPUÉS de una palabra se confundía con
            # la de antes (2026-11-16, escena 9: "recording." tomaba el arranque de "Explain").
            if not (k == 0 or (prev and prev.display[-1:] in ".,;:!?—…")):
                continue
            # adelante: hay una pausa real entre el inicio de Whisper y el siguiente arranque de voz
            fwd = on_t[(on_t > g0) & (on_t <= g0 + SNAP_MAX_S)]
            new0 = None
            i0 = idx(g0)
            if fwd.size and (~sp[i0:idx(fwd[0])]).any() and fwd[0] < g1 - 0.03:   # "A", "The": palabras cortas
                new0 = float(fwd[0])
            else:
                # atrás: Whisper llegó tarde (medido +280..+360 ms) y la voz arrancó tras una pausa poco
                # antes. La pausa tiene que ser posterior al INICIO de la palabra anterior (Whisper suele
                # estirar el final de esa palabra dentro de la pausa, así que su final no sirve de límite).
                back = on_t[(on_t < g0) & (on_t >= g0 - SNAP_MAX_S) & (on_t > prev_start + 0.1)
                            & (on_t >= sc.audio_offset)]
                if back.size:
                    new0 = float(back[-1])
                    if prev and sc.audio_offset + prev.end > new0:          # recorta el final estirado
                        prev.end = max(prev.start + 0.05, new0 - sc.audio_offset - 0.01)
            if new0 is not None and abs(new0 - g0) >= 0.02:
                note(sc, u, "start", g0, new0)
                u.start = new0 - sc.audio_offset
                moved_starts += 1
    # 2) finales: si la voz sigue tras el fin de Whisper y se apaga antes de la palabra siguiente
    for sc in scenes:
        for k, u in enumerate(sc.units):
            if u.end is None:
                continue
            g1 = sc.audio_offset + u.end
            nxt = sc.audio_offset + sc.units[k + 1].start if k + 1 < len(sc.units) and sc.units[k + 1].start is not None \
                else sc.audio_offset + sc.audio_s + 0.3
            if not sp[idx(g1)]:
                continue
            ahead = off_t[(off_t > g1) & (off_t <= g1 + SNAP_MAX_S)]
            if ahead.size and ahead[0] <= nxt + 0.02 and ahead[0] - g1 >= 0.03:
                note(sc, u, "end", g1, float(ahead[0]))
                u.end = float(ahead[0]) - sc.audio_offset
                moved_ends += 1
    big = [a for a in adjustments if abs(a["ms"]) >= 100]
    return {"starts_moved": moved_starts, "ends_moved": moved_ends,
            "median_start_shift_ms": int(np.median([a["ms"] for a in adjustments if a["edge"] == "start"]))
            if moved_starts else 0,
            "adjustments_ge_100ms": big}


def non_whisper_words(scenes: list) -> list[dict]:
    """Words whose timing does NOT come from a word measured by Whisper, with their time in the
    video (to check them by hand). Uses the final timings of the on-screen word
    (after refine_with_energy if it already ran)."""
    out = []
    for sc in scenes:
        for w in sc.word_report:
            if w["method"] != "whisper":
                u = sc.units[w["unit"]]
                out.append({"scene": sc.index, "word": w["word"], "spoken": w["spoken"],
                            "video_start": round(sc.audio_offset + u.start, 2),
                            "video_end": round(sc.audio_offset + u.end, 2), "method": w["method"]})
    return out

"""Shorts subtitles: word-by-word karaoke burned in with libass (1080×1920).

Groups of 2–4 words, one line, centered in the middle third (y ≈ 960); the word being spoken in accent
(#2563EB), the rest in textTitle (#0B1220); Inter 700 at 110 (ASS size); no box, soft shadow (the same
no-box style as the long-form callouts, assemble.ass_style). Times come from the aligned words
(Whisper + script, align.py), so the active word follows the voice.

Usage (for a future `--format short`):
    words = karaoke.words_from_scenes(scenes, t0, t1)     # aligned units between t0 and t1, time 0 = t0
    info = karaoke.build_karaoke_ass(words, Path("short.ass"))
    # burn with assemble.burn_filter("short.ass", "fonts") after assemble.copy_caption_fonts(dir, ("body_700",))
"""
from __future__ import annotations

from pathlib import Path

from . import theme_paper
from .assemble import (SUB_LEAD_S, _clean, _sub_break_cost, _sub_punct, _ts_ass, ass_header, ass_style,
                       ass_text_px, caption_ass_colors)

W, H = 1080, 1920
FONT_KEY = "body_700"
SIZE = theme_paper.SCALE["karaoke_px"]          # 110 (ASS: winAscent + winDescent = 110 px; em ≈ 77 px)
CENTER_Y = H // 2                               # centro del tercio medio (640–1280)
MARGIN_H = 90                                   # margen lateral: ancho útil 900 px (botones de Shorts a la derecha)
MAX_W_PX = W - 2 * MARGIN_H
GROUP_WORDS = (2, 4)
GAP_FILL_S = 0.25                               # huecos menores entre grupos se rellenan (sin parpadeo)


def words_from_scenes(scenes: list, t0: float = 0.0, t1: float | None = None) -> list[dict]:
    """Aligned units of the scenes whose audio falls in [t0, t1) of the long-form timeline, with times
    relative to t0: [{text, start, end, keyword, brace}]. A {shown|spoken} unit is one word (never split)."""
    out = []
    for sc in scenes:
        for u in sc.units:
            if u.start is None or u.end is None:
                continue
            a, b = sc.audio_offset + u.start, sc.audio_offset + u.end
            if a < t0 or (t1 is not None and a >= t1):
                continue
            out.append({"text": u.display, "start": round(a - t0, 3), "end": round(b - t0, 3),
                        "keyword": u.keyword, "brace": u.brace})
    return out


def _px(text: str) -> float:
    return ass_text_px(text, theme_paper.FONT_FILES[FONT_KEY], SIZE)


class _U:                                       # adaptador para las reglas de corte de assemble
    def __init__(self, w: dict):
        self.display, self.keyword = w["text"], w.get("keyword", False)


def group_words(words: list[dict]) -> list[list[dict]]:
    """Optimal split into groups of 2–4 words on one line (dynamic programming, like the SRT phrases).
    Hard: a group fits MAX_W_PX at SIZE (a single word may not, then it goes alone); never more than 4 words;
    a group never runs across the end of a sentence. Soft: the same break costs as the subtitles
    (assemble._sub_break_cost: best after punctuation, then before a conjunction/preposition; never after
    a, the, of, to...), 1-word groups only when forced, 2–3 words preferred over 4. A {shown|spoken} unit is
    one word and is never split."""
    U = [_U(w) for w in words]
    n = len(U)
    lo, hi = GROUP_WORDS
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        end_cost = _sub_break_cost(U, j)
        for i in range(max(0, j - hi), j):
            g = U[i:j]
            if len(g) > 1 and _px(" ".join(u.display for u in g)) > MAX_W_PX:
                continue
            c = 2.0 + end_cost
            c += 50.0 * sum(1 for u in g[:-1] if _sub_punct(u) in tuple(".?!…"))   # cruza un fin de oración
            if len(g) < lo:
                c += 6.0
            elif len(g) == hi:
                c += 0.5
            if best[i] + c < best[j]:
                best[j], back[j] = best[i] + c, i
    out, j = [], n
    while j > 0:
        out.append(words[back[j]:j])
        j = back[j]
    return out[::-1]


def karaoke_events(groups: list[list[dict]], C: dict | None = None) -> list[dict]:
    """One event per active word: [{start, end, active (index), group (index), text (ASS)}]. A group appears
    SUB_LEAD_S before its first word and stays until the next group appears (if the gap is < GAP_FILL_S)
    or until its last word ends; each word is active from its start to the next word's start."""
    C = C or caption_ass_colors()
    base, act = C["karaoke_text"], C["karaoke_active"]
    evs = []
    for gi, g in enumerate(groups):
        g0 = max(0.0, g[0]["start"] - SUB_LEAD_S)
        g1 = g[-1]["end"]
        if gi + 1 < len(groups):
            n0 = max(0.0, groups[gi + 1][0]["start"] - SUB_LEAD_S)
            if n0 - g1 < GAP_FILL_S:
                g1 = n0
        for k, w in enumerate(g):
            s0 = g0 if k == 0 else w["start"]
            s1 = g[k + 1]["start"] if k + 1 < len(g) else g1
            if s1 - s0 < 0.02:
                continue
            parts = [(f"{{\\c{act}&}}{_clean(x['text'])}{{\\c{base}&}}" if j == k else _clean(x["text"]))
                     for j, x in enumerate(g)]
            evs.append({"start": round(s0, 3), "end": round(s1, 3), "group": gi, "active": k,
                        "text": f"{{\\q2\\an5\\pos({W // 2},{CENTER_Y})\\c{base}&}}" + " ".join(parts)})
    return evs


def build_karaoke_ass(words: list[dict], ass_path: Path) -> dict:
    """Writes the karaoke ASS for a 1080×1920 Short from aligned words (words_from_scenes). Returns info
    for the manifest (groups, events, style)."""
    C = caption_ass_colors()
    groups = group_words(words)
    evs = karaoke_events(groups, C)
    style = ass_style("Karaoke", FONT_KEY, SIZE, C["karaoke_text"], C["karaoke_active"], 5, MARGIN_H, 0)
    lines = [f"Dialogue: 0,{_ts_ass(e['start'])},{_ts_ass(e['end'])},Karaoke,,0,0,0,,{e['text']}" for e in evs]
    Path(ass_path).write_text(ass_header(W, H, [style]) + "\n".join(lines) + "\n", encoding="utf-8")
    too_wide = [" ".join(x["text"] for x in g) for g in groups if _px(" ".join(x["text"] for x in g)) > MAX_W_PX]
    return {"format": f"{W}x{H}", "font": theme_paper.FONT_FACES[FONT_KEY] + " Bold",
            "font_file": Path(theme_paper.FONT_FILES[FONT_KEY]).name, "size_ass": SIZE, "center_y": CENTER_Y,
            "max_width_px": MAX_W_PX, "style": style, "groups": [" ".join(x["text"] for x in g) for g in groups],
            "events": len(evs), "one_word_groups": sum(1 for g in groups if len(g) == 1), "too_wide": too_wide}

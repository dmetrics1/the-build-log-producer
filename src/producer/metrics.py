"""Measured numbers the video claims (cost, electricity, time, VRAM), read from the manifest.

Reference = the run's last COLD pass (no cache: all narration synthesized and all
EXPLAIN scenes rendered). A cached pass takes seconds and does not represent "from script to
MP4". The diagrams receive these numbers as METRICS (explain.render_explain) and the script is checked
against them: a scene with `| metrics=software,electricity` declares that its {number|voice} groups, in
order, match those metrics; if they don't, a warning goes to subtitle_check.md and the manifest.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

KEYS = ("software", "electricity", "wall", "vram_peak", "tts_vram")


def _stage(entry: dict, name: str) -> dict:
    return next((s for s in entry.get("stages", []) if s.get("name") == name), {})


def is_cold(entry: dict) -> bool:
    s = entry.get("summary") or {}
    if "cold" in s:
        return bool(s["cold"])
    ex = s.get("explain") or {}                       # pasadas anteriores al flag: se infiere
    return bool(ex) and ex.get("rendered") == ex.get("scenes") and _stage(entry, "tts").get("seconds", 0) > 10


def fmt_wall(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m} min {s} s" if m else f"{s} s"


def fmt_gb(mib: float) -> str:
    return f"{mib / 1024:.1f} GB"


def fmt_cents(usd: float) -> str:
    return f"{usd * 100:.1f}¢"


def fmt_usd(usd: float) -> str:
    return "$0" if usd == 0 else f"${usd:.2f}"


def reference_metrics(manifest_path: Path) -> dict | None:
    """METRICS of the last cold pass recorded in manifest_path (and its history); None if there is none."""
    if not manifest_path.exists():
        return None
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    passes = list(m.get("previous_passes", [])) + [m]
    passes = [p for p in passes if p.get("status") == "done" and is_cold(p)]
    if not passes:
        return None
    ref = passes[-1]
    s, c = ref.get("summary", {}), ref.get("costs", {})
    wall = s.get("wall_seconds") or s.get("total_seconds")
    vram = s.get("vram_peak_mib")
    tts_vram = _stage(ref, "tts").get("vram_peak_mib")
    if wall is None or vram is None:
        return None
    soft, elec = float(c.get("software_usd", 0.0)), float(c.get("electricity_usd", 0.0))
    chk = _stage(ref, "subtitles").get("check") or {}
    if chk.get("phrases") is None:                   # pasadas antiguas resumidas sin el dato: la última del run
        chk = _stage(m, "subtitles").get("check") or {}
    return {
        "phrases": chk.get("phrases"), "flagged": chk.get("flagged"),
        "pass": ref.get("pass"), "cold": True, "finished_at": ref.get("finished_at"),
        "software_usd": soft, "electricity_usd": elec, "wall_s": wall,
        "vram_peak_mib": vram, "tts_vram_mib": tts_vram,
        "display": {"software": fmt_usd(soft), "electricity": fmt_cents(elec), "wall": fmt_wall(wall),
                    "vram_peak": fmt_gb(vram), "tts_vram": fmt_gb(tts_vram) if tts_vram else None},
        "values": {"vram_peak_gb": round(vram / 1024, 1),
                   "tts_vram_gb": round(tts_vram / 1024, 1) if tts_vram else None},
    }


def _norm(s: str) -> str:
    return re.sub(r"[\s≈~]+", "", str(s)).lower()


def check_script(scenes: list, metrics: dict | None) -> list[dict]:
    """Compares the script's numbers ({number|voice} in scenes with `| metrics=...`) with the reference."""
    rows = []
    for sc in scenes:
        keys = [k.strip() for k in str(sc.params.get("metrics", "")).split(",") if k.strip()]
        if not keys:
            continue
        for k, shown in zip(keys, sc.braces + [None] * len(keys)):
            real = metrics["display"].get(k) if metrics else None
            if k not in KEYS:
                status = f"unknown metric '{k}' (valid: {', '.join(KEYS)})"
            elif metrics is None:
                status = "no cold reference pass yet"
            elif shown is None:
                status = "the scene has no {number|voice} for this metric"
            else:
                status = "ok" if _norm(shown) == _norm(real) else "MISMATCH"
            rows.append({"scene": sc.index, "explain_id": sc.explain_id, "metric": k, "script": shown,
                         "manifest": real, "status": status})
    return rows


def check_markdown(rows: list[dict], metrics: dict | None) -> str:
    ref = (f"cold pass {metrics['pass']} ({metrics.get('finished_at')})" if metrics
           else "none (a cold pass is missing)")
    bad = [r for r in rows if r["status"] != "ok"]
    out = ["", "## Script numbers vs manifest", "",
           f"Reference: {ref}. The diagrams show the manifest value; the narration and "
           f"subtitles show the script value. **{len(bad)} warning(s).**", "",
           "| scene | metric | script | manifest | status |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        st = r["status"] if r["status"] == "ok" else f"**WARNING: {r['status']}**"
        out.append(f"| {r['scene']} ({r['explain_id'] or ''}) | {r['metric']} | {r['script']} | {r['manifest']} | {st} |")
    return "\n".join(out) + "\n"


def latest_cold_reference(runs_root: Path) -> tuple[dict | None, str | None]:
    """reference_metrics of the most recent cold pass across ALL runs (main manifests). Used for the
    {{ }} figures of a script whose own run has no cold pass yet. Returns (metrics, run folder name)."""
    best, src = None, None
    for mf in sorted(Path(runs_root).glob("*/manifest.json")):
        r = reference_metrics(mf)
        if r and (best is None or (r.get("finished_at") or "") > (best.get("finished_at") or "")):
            best, src = r, mf.parent.name
    return best, src


# ---------------------------------------------------------------- {{ }} en los guiones
_ONES = "zero one two three four five six seven eight nine".split()


def _words(n: int) -> str:
    from num2words import num2words
    return num2words(n).replace(",", "")


def _decimal_words(x: str) -> str:
    """'2.3' -> 'two point three'; '0.1' -> 'zero point one'; '61' -> 'sixty-one'."""
    if "." in x:
        i, d = x.split(".", 1)
        return f"{_words(int(i))} point " + " ".join(_ONES[int(ch)] for ch in d)
    return _words(int(x))


def spoken(display: str) -> str:
    """How the narration reads a displayed figure ('0.1¢', '$0', '2 min 41 s', '2.3 GB', '61')."""
    t = display.strip()
    if m := re.fullmatch(r"\$(\d+(?:\.\d+)?)", t):
        return f"{_decimal_words(m.group(1))} dollars"
    if m := re.fullmatch(r"(\d+(?:\.\d+)?)¢", t):
        n = m.group(1)
        return f"{_decimal_words(n)} {'cent' if n == '1' else 'cents'}"
    if m := re.fullmatch(r"(?:(\d+) min )?(\d+) s", t):
        mins, secs = m.group(1), int(m.group(2))
        sec = f"{_words(secs)} {'second' if secs == 1 else 'seconds'}"
        if not mins:
            return sec
        mn = int(mins)
        return f"{_words(mn)} {'minute' if mn == 1 else 'minutes'} and {sec}"
    if m := re.fullmatch(r"(\d+(?:\.\d+)?) GB", t):
        return f"{_decimal_words(m.group(1))} gigabytes"
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return _decimal_words(t)
    raise ValueError(f"no spoken form for figure {display!r}")


# alias en el guion -> texto en pantalla
FIGURES = {
    "software": lambda r: r["display"]["software"],
    "elec": lambda r: r["display"]["electricity"],
    "electricity": lambda r: r["display"]["electricity"],
    "wall": lambda r: r["display"]["wall"],
    "vram": lambda r: r["display"]["vram_peak"],
    "vram_peak": lambda r: r["display"]["vram_peak"],
    "tts_vram": lambda r: r["display"]["tts_vram"],
    "phrases": lambda r: str(r["phrases"]) if r.get("phrases") is not None else None,
    "flagged": lambda r: str(r["flagged"]) if r.get("flagged") is not None else None,
}


def figure_units(ref: dict | None) -> dict[str, str]:
    """{alias: '{display|spoken}'} for the {{alias}} placeholders of a script."""
    if not ref:
        return {}
    out = {}
    for k, f in FIGURES.items():
        d = f(ref)
        if d:
            out[k] = "{" + d + "|" + spoken(d) + "}"
    return out

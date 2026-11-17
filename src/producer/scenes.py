"""Script parser (scripts/*.md) -> metadata + list of scenes.

Format (see the comment at the top of scripts/test_script.md):
  ---front matter---      title, slug, music, affiliate_links (voice, speed and target_seconds are only
                          recorded: voice and speed come from config.toml)
  [KIND: ... | k=v | keep] scene options (SCREEN: src, in, out, zoom; keep in merges)
  # section               not narrated; marks timing and retention role
  [SCREEN: description]   screen scene
  [EXPLAIN: concept]      explainer scene (explainroo); ordinal x01, x02...
  [CALLOUT: a *word* b]   on-screen callout (3–6 words, one *keyword*) for the phrase that contains the
                          next narrated word of this scene; replaces the automatic one. Only burned in
                          over SCREEN scenes (never over EXPLAIN). Not narrated.
  *word*                  keyword: accent in the callout (and in the Shorts karaoke source)
  {screen|voice}          what is shown | what is said; voice = "/phonemes/" -> [screen](/phonemes/)
  # Metadata              nothing is narrated from here on
Pronunciation: config/pronounce.toml [words] changes what the voice SAYS for single words
(not inside {a|b}); the subtitle does not change. See that file's header.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TAG = re.compile(r"^\[(SCREEN|EXPLAIN):\s*(.*)\]\s*$")
CALLOUT = re.compile(r"^\[CALLOUT:\s*(.*?)\s*\]\s*$")
BRACE = re.compile(r"\{([^|{}]*)\|([^{}]*)\}")
PUNCT_ONLY = re.compile(r"^[^\w$¢€£%]+$")
EDGE_PUNCT = re.compile(r"^([^\w$¢€£%]*)(.*?)([^\w$¢€£%]*)$")   # puntuación inicial, palabra, final
PHONEMES = re.compile(r"^/[^/\s]+/$")                           # "/kˈOkOɹO/": fonemas misaki
PRONOUNCE_PATH = Path(__file__).resolve().parents[2] / "config" / "pronounce.toml"
DISCLOSURE_SPOKEN = "Some links in the description are affiliate links."
DISCLOSURE_OVERLAY = "Affiliate link in description"   # mismo texto que config.toml [affiliates]


@dataclass
class Unit:
    display: str              # texto del subtítulo (con puntuación pegada)
    value: str                # texto sin puntuación añadida (para cifras {a|b})
    spoken: list[str]         # palabras que dice la voz
    keyword: bool = False
    brace: bool = False
    pron: bool = False        # voz cambiada por config/pronounce.toml (align empareja con `value`)
    start: float | None = None    # segundos dentro del audio de la escena
    end: float | None = None


@dataclass
class Scene:
    index: int
    kind: str                 # "SCREEN" | "EXPLAIN"
    label: str
    section: str
    raw: str = ""
    units: list[Unit] = field(default_factory=list)
    explain_id: str | None = None
    overlay: str | None = None
    keep: bool = False            # en una fusión por duración mínima, conservar este visual
    params: dict = field(default_factory=dict)   # opciones de la etiqueta: [SCREEN: ... | k=v | flag]
    # [CALLOUT: ...] del guion: {"unit": índice de la primera unidad narrada tras la línea, "text", "units"}
    callouts: list = field(default_factory=list)
    absorbed_by: int | None = None               # escena cuyo visual cubre esta narración
    word_report: list = field(default_factory=list)
    narr_start_frame: int = 0     # límites de SU narración (los de visual pueden cambiar al fusionar)
    narr_frames: int = 0
    # se llenan en tts / timeline / render
    audio_path: Path | None = None
    audio_s: float = 0.0
    start_frame: int = 0
    frames: int = 0
    audio_offset: float = 0.0     # segundos globales donde empieza su voz
    clip: Path | None = None
    align_ratio: float | None = None

    @property
    def spoken_text(self) -> str:
        return " ".join(w for u in self.units for w in u.spoken)

    @property
    def display_text(self) -> str:
        return " ".join(u.display for u in self.units)

    @property
    def keywords(self) -> list[str]:
        return [u.value for u in self.units if u.keyword]

    @property
    def braces(self) -> list[str]:
        return [u.value for u in self.units if u.brace]

    @property
    def id(self) -> str:
        return f"s{self.index:02d}"


def load_pronunciations(path: Path | None = None) -> dict[str, str]:
    """config/pronounce.toml [words] -> {lowercase word: pronunciation}. No file: {}."""
    path = Path(path) if path else PRONOUNCE_PATH
    if not path.exists():
        return {}
    import tomllib
    with open(path, "rb") as f:
        words = tomllib.load(f).get("words", {})
    out = {}
    for word, pron in words.items():
        pron = str(pron).strip()
        if not pron:
            raise ValueError(f"{path.name}: empty pronunciation for {word!r}")
        if PHONEMES.match(pron):
            try:
                from misaki.en import GB_VOCAB, US_VOCAB
                bad = set(pron.strip("/")) - US_VOCAB - GB_VOCAB
            except ImportError:
                bad = set()
            if bad:
                raise ValueError(f"{path.name}: {word!r} uses symbols unknown to misaki: {sorted(bad)}")
        out[word.lower()] = pron
    return out


def pron_spoken(word: str, pron: str) -> str:
    """Text sent to Kokoro: "/phonemes/" -> "[word](/phonemes/)" (misaki phoneme link);
    a respelling ("explain roo") is spoken as is."""
    return f"[{word}]({pron})" if PHONEMES.match(pron) else pron


def _plain(text: str, kw: bool, units: list[Unit], pronounce: dict[str, str] | None = None) -> None:
    for tok in text.split():
        if PUNCT_ONLY.match(tok) and units:
            units[-1].display += tok
            units[-1].spoken[-1] += tok
            continue
        lead, core, trail = EDGE_PUNCT.match(tok).groups()
        pron = (pronounce or {}).get(core.lower()) if core else None
        if pron:   # la puntuación pegada se queda en la voz: marca pausas y entonación
            units.append(Unit(display=tok, value=tok, spoken=(lead + pron_spoken(core, pron) + trail).split(),
                              keyword=kw, pron=True))
        else:
            units.append(Unit(display=tok, value=tok, spoken=[tok], keyword=kw))


def parse_units(raw: str, pronounce: dict[str, str] | None = None) -> list[Unit]:
    """pronounce: {lowercase word: pronunciation} (load_pronunciations) for single words;
    {a|b} groups do not use it."""
    parts = raw.split("*")
    if len(parts) % 2 == 0:
        raise ValueError(f"unbalanced asterisks in: {raw!r}")
    units: list[Unit] = []
    for i, part in enumerate(parts):
        kw = i % 2 == 1
        pos = 0
        for m in BRACE.finditer(part):
            _plain(part[pos:m.start()], kw, units, pronounce)
            shown, spoken = m.group(1), m.group(2).strip()
            if PHONEMES.match(spoken):
                spoken = pron_spoken(shown.strip(), spoken)
            units.append(Unit(display=shown, value=shown, spoken=spoken.split(), keyword=kw, brace=True))
            pos = m.end()
        _plain(part[pos:], kw, units, pronounce)
    return units


def _front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta: dict = {}
    for line in fm.strip().splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        val = re.sub(r"\s+#.*$", "", val).strip()
        try:
            meta[key.strip()] = json.loads(val)
        except json.JSONDecodeError:
            meta[key.strip()] = val.strip('"').strip("'")
    return meta, body


def read_meta(path: Path) -> dict:
    """Front matter only (slug, music…), before the figures are known."""
    return _front_matter(Path(path).read_text(encoding="utf-8"))[0]


FIGURE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def parse_script(path: Path, pronounce: dict[str, str] | None = None,
                 figures: dict[str, str] | None = None) -> tuple[dict, list[Scene]]:
    """pronounce=None loads config/pronounce.toml; {} disables it.
    figures: {alias: '{display|spoken}'} for the {{alias}} placeholders (metrics.figure_units); a
    placeholder without a measured figure stops the run (the video never says a number nobody measured)."""
    if pronounce is None:
        pronounce = load_pronunciations()
    text = Path(path).read_text(encoding="utf-8")
    meta, body = _front_matter(text)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    missing = sorted({k for k in FIGURE_RE.findall(body) if k not in (figures or {})})
    if missing:
        raise ValueError(f"figures {missing} have no measured value (they come from the last cold pass, "
                         f"metrics.latest_cold_reference); available: {sorted(figures or {})}")
    body = FIGURE_RE.sub(lambda m: figures[m.group(1)], body)
    scenes: list[Scene] = []
    section, cur, n_explain = "", None, 0
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("# "):
            section = line[2:].strip()
            if section.lower().startswith("metadata"):
                break
            cur = None
            continue
        mc = CALLOUT.match(line)
        if mc:
            if cur is None:
                raise ValueError(f"[CALLOUT: {mc.group(1)}] outside a scene: put it after a [SCREEN: ...] tag")
            cur.callouts.append({"offset": len(cur.raw), "text": mc.group(1)})
            continue
        m = TAG.match(line)
        if m:
            label, *opts = [p.strip() for p in m.group(2).split(" | ")]
            params = dict(o.split("=", 1) if "=" in o else (o, True) for o in opts if o)
            cur = Scene(index=len(scenes) + 1, kind=m.group(1), label=label, section=section,
                        keep=bool(params.pop("keep", False)), params=params)
            if cur.kind == "EXPLAIN":
                if params.get("id"):                     # | id=xcc : id fijo; no corre la numeración x01, x02…
                    cur.explain_id = str(params.pop("id"))
                else:
                    n_explain += 1
                    cur.explain_id = f"x{n_explain:02d}"
            scenes.append(cur)
            continue
        if line and cur is not None:
            cur.raw = (cur.raw + " " + line).strip()
    for sc in scenes:
        sc.units = parse_units(sc.raw, pronounce)
        if not sc.units:
            raise ValueError(f"scene {sc.index} has no narration: [{sc.kind}: {sc.label}]")
        for co in sc.callouts:
            try:
                co["units"] = parse_units(co["text"])
                co["unit"] = len(parse_units(sc.raw[:co.pop("offset")], pronounce))
            except ValueError as e:
                raise ValueError(f"scene {sc.index}: [CALLOUT: {co['text']}]: {e}") from None
            if not co["units"]:
                raise ValueError(f"scene {sc.index}: empty [CALLOUT: ]")
    return meta, scenes


def plan_shots(scenes: list[Scene], fps: int, min_s: float = 2.5) -> list[dict]:
    """Minimum shot length. A scene whose narration lasts less than min_s is merged
    with the previous one in its section (or with the next one if it is the first): a single
    visual covers both narrations, which do not change. Visual kept: that of the scene marked
    `| keep`, otherwise that of the first in the group. Returns the changes for the manifest."""
    groups: list[list[Scene]] = []
    for sc in scenes:
        short = sc.narr_frames / fps < min_s
        if short and groups and groups[-1][-1].section == sc.section:
            groups[-1].append(sc)
        else:
            groups.append([sc])
    # un grupo que sigue corto (primera escena de su sección) se une al siguiente de su sección
    i = 0
    while i < len(groups) - 1:
        g, nxt = groups[i], groups[i + 1]
        if sum(s.narr_frames for s in g) / fps < min_s and g[0].section == nxt[0].section:
            groups[i] = g + nxt
            del groups[i + 1]
        else:
            i += 1
    changes = []
    for g in groups:
        if len(g) == 1:
            continue
        kept = next((s for s in g if s.keep), g[0])
        total = sum(s.narr_frames for s in g)
        start = g[0].narr_start_frame
        for s in g:
            if s is kept:
                s.start_frame, s.frames, s.absorbed_by = start, total, None
            else:
                s.frames, s.absorbed_by = 0, kept.index
        changes.append({"scenes": [s.index for s in g],
                        "short": [{"scene": s.index, "duration_s": round(s.narr_frames / fps, 2)}
                                  for s in g if s.narr_frames / fps < min_s],
                        "visual_kept": {"scene": kept.index, "kind": kept.kind, "explain_id": kept.explain_id},
                        "visual_dropped": [{"scene": s.index, "kind": s.kind, "explain_id": s.explain_id}
                                           for s in g if s is not kept],
                        "shot_s": round(total / fps, 2)})
    return changes


def apply_affiliate_disclosure(meta: dict, scenes: list[Scene], programs: list[dict] | None = None,
                               disclosure: dict | None = None) -> dict:
    """Channel rule: the disclosure goes in ONLY when there are affiliate links, i.e.
    when the script mentions an approved program from config/affiliates.toml or declares
    affiliate_links in the front matter. Inserts a spoken line + on-screen text in the
    first scene after the hook (the pipeline checks that it starts before 30 s)."""
    programs = programs or []
    disclosure = disclosure or {}
    links = list(meta.get("affiliate_links") or []) + [p["url"] for p in programs if p["url"] not in
                                                        (meta.get("affiliate_links") or [])]
    if not links:
        return {"inserted": False, "reason": "no approved program mentions and no affiliate_links"}
    spoken = disclosure.get("spoken", DISCLOSURE_SPOKEN)
    overlay = disclosure.get("on_screen", DISCLOSURE_OVERLAY)
    first_section = scenes[0].section
    target = next((s for s in scenes if s.section != first_section), scenes[0])
    first_unit = len(target.units)
    target.units += parse_units(spoken)
    target.overlay = overlay
    return {"inserted": True, "scene": target.index, "first_unit": first_unit, "links": links,
            "programs": [p["id"] for p in programs], "spoken": spoken, "overlay": overlay}

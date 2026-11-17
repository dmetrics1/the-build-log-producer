"""Animated SCREEN scenes with real content from this machine, in the "paper" theme (theme_paper.py).

Look: light background with a 48 px grid; files and images on white cards (radius, 2 px border and the
design system's soft shadow); terminal as a DARK card (dark-theme surface, ">" prompt in its accent2).
Optional heading and eyebrow in Space Grotesk; code and terminal in JetBrains Mono.
Motion (theme_paper.MOTION): the card enters with an ease-out slide-up + fade; in the terminal the command
is typed at 35 ms/character with a blinking cursor, then the output appears line by line; in files, the
highlight arrives with a short fade. Every clip carries its SFX track (swoosh when the card enters, tick when
each typewriter ends; sfx.place) even if it is silent.

Rule: only what really exists is shown (project files, real command output saved in
assets/screens/, real frames). No made-up output.

Syntax (tag options; scenes.py puts them in scene.params):

  [SCREEN: label | show=file | path=src/producer/align.py | lines=1-16 | hl=3-4]
  [SCREEN: label | show=file | path=runs/x/manifest.json | find="previous_passes">"stages" | skip=7 | n=18]
  [SCREEN: label | show=terminal | capture=assets/screens/doctor_ok.txt | mark=0 FAIL | size=40]
  [SCREEN: label | show=image | path=assets/screens/frame_subtitle.png | title=final.mp4 at 0:06.7]

  show=file       project file with line numbers and syntax colors (Python, Markdown, JSON).
    path=         path relative to the project root (never secrets/ or .env*).
    lines=a-b     line range of the file (1 = first).
    find=A>B      without lines: start at the first line containing A, then the next one with B...
    skip=k  n=k   offset from the anchor (may be negative) and how many lines to show
                  (default: as many as fit).
  show=terminal   plain-text capture in assets/screens/*.txt:
                    "$ command"  command line (prompt + typewriter);
                    "#! note"    our annotation, not program output (drawn dimmed, as "# note");
                    the rest     real output; OK / WARN / FAIL are colored (term_ok / term_warn / term_fail),
                                 dollar figures in term_warn.
    capture=      path of the capture.  lines=a-b  capture lines (1 = first line of the file).
    wrap          wraps long output lines (at ", " when possible) instead of cutting them with "…".
    prompt=       prompt text (default ">").
  show=image      image (a real frame) in a framed card, with a slow zoom-in (1.00 -> 1.035).
    path=         path of the image.

  Common:  title=  card title · hl=a-b,c  lines highlighted by number (of the file or the
  capture) · mark=t1,t2  highlights lines containing that text · highlight=w1,w2  highlights those
  words (case-sensitive) · size=N  font size in px at 1080p (minimum 28) ·
  heading=  large heading above the card (Space Grotesk 700, typewriter); *word* is drawn in the
  keyword color · eyebrow=  short eyebrow above the heading or the card.
  Values cannot contain " | " and lists are comma-separated.

Layout: all content stays above assemble.SCREEN_PANEL_FRAC·H (below it: the 100 px callout strip and the free bottom 20 %), also
during the entrance (anything peeking below is clipped); body text >= 28 px at 1080p.
All of the panels' own text (headers, eyebrows, placeholder) is in English, like the channel.
User paths are shortened (%USERPROFILE%, %LOCALAPPDATA%, …\\04_Youtube_IA) in all text.
"""
from __future__ import annotations

import hashlib
import io
import keyword
import math
import os
import re
import subprocess
import time
import tokenize
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import theme_paper as tp
from .config import PROJECT_ROOT

VERSION = 3          # subir al cambiar el diseño o la animación de los paneles (invalida su caché)
S = 2                # capas estáticas dibujadas a 2x y reducidas con lanczos a 1080p
MIN_PX, MAX_PX = 28, 40
LH = 1.25            # interlineado del código / terminal
SLIDE_PX = 32        # recorrido del slide-up de entrada
ENTER_S = 0.30       # entrada de tarjeta (dentro de MOTION enter_min_s..enter_max_s)
LINE_FADE_S = 0.25   # fundido de cada línea de salida
STAGGER_S = 0.05     # escalonado entre líneas de salida
ENTER_PAUSE_S = 0.18 # "Enter": pausa entre el fin del comando y la primera línea de salida
HL_DELAY_S = 0.30    # el resaltado llega este tiempo después de que todo está a la vista
HL_FADE_S = 0.25
IMG_ZOOM = 1.035     # acercamiento lento de la imagen dentro de su marco
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

WINFONTS = Path(r"C:\Windows\Fonts")
_FALLBACK = {                       # solo si falta el archivo de theme_paper.FONT_FILES
    "heading_700": ("segoeuib.ttf", "arialbd.ttf"), "heading_500": ("segoeuisb.ttf", "arial.ttf"),
    "body_400": ("segoeui.ttf", "arial.ttf"), "body_500": ("segoeui.ttf", "arial.ttf"),
    "body_600": ("segoeuisb.ttf", "arialbd.ttf"), "body_700": ("segoeuib.ttf", "arialbd.ttf"),
    "mono_400": ("consola.ttf", "cour.ttf"),
    "mono_700": ("consolab.ttf", "courbd.ttf"),
}


def font_files() -> dict[str, Path | None]:
    """Font per role: the theme's if it exists in assets/fonts/, otherwise a Windows font (with a warning)."""
    out = {}
    for k, p in tp.FONT_FILES.items():
        p = Path(p)
        out[k] = p if p.exists() else next((WINFONTS / n for n in _FALLBACK.get(k, ()) if (WINFONTS / n).exists()), None)
    return out


def fonts_missing() -> list[str]:
    return [Path(p).name for p in tp.FONT_FILES.values() if not Path(p).exists()]


@lru_cache(maxsize=512)
def _font_at(path: str | None, px: int):
    return ImageFont.truetype(path, px) if path else ImageFont.load_default()


class _Fonts:
    def __init__(self):
        self.files = font_files()

    def __call__(self, role: str, px: float):
        """Font for drawing at S×: `px` in 1080p px."""
        p = self.files.get(role)
        return _font_at(str(p) if p else None, round(px * S))


# ---------------------------------------------------------------- colores (todos de theme_paper)

def _rgb(v: str) -> tuple[int, int, int]:
    return tp.rgba(v)[:3]


def _colors() -> dict:
    P = tp.palette()
    C = {k: _rgb(v) for k, v in P.items()}
    C.update({
        "head_bg": tp.over(P["bg"], P["card_bg"], 0.55),          # franja de cabecera de la tarjeta clara
        "gutter": tp.over(P["muted"], P["card_bg"], 0.70),
        "hl_line": tp.over(P["accent"], P["card_bg"], 0.08),
        "hl_word": tp.over(P["accent"], P["card_bg"], 0.16),
        "pill": tp.over(P["accent"], P["card_bg"], 0.08),
        "t_border": tp.over(tp.dark()["cardBorder"], P["term_bg"]),
        "t_hl_line": tp.over(P["term_hl"], P["term_bg"], 0.30),
        "t_hl_word": tp.over(P["term_hl"], P["term_bg"], 0.75),
        "t_fail_line": tp.over(P["term_fail"], P["term_bg"], 0.14),
        "t_dot": tp.over(P["term_muted"], P["term_bar"], 0.45),
    })
    return C


def _shadow_spec() -> tuple[int, int, float, tuple[int, int, int], float]:
    """CARD["shadow"] ("0 2px 8px rgba(15,23,42,0.06)") -> (dx, dy, blur, rgb, alpha)."""
    m = re.match(r"\s*(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)(?:px)?\s+(.+)$", tp.CARD["shadow"])
    if not m:
        return 0, 2, 8.0, (15, 23, 42), 0.06
    r, g, b, a = tp.rgba(m.group(4))
    return round(float(m.group(1))), round(float(m.group(2))), float(m.group(3)), (r, g, b), a


# ---------------------------------------------------------------- utilidades

def redact(text: str) -> str:
    """Shortens personal paths (user, institution) to variables or to …\\04_Youtube_IA."""
    home = Path.home()
    lad = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
    pairs = [(str(PROJECT_ROOT), "…\\" + PROJECT_ROOT.name), (lad, "%LOCALAPPDATA%"), (str(home), "%USERPROFILE%")]
    short = re.compile(r"C:\\Users\\[A-Z0-9]{1,6}~\d", re.I)
    for src, dst in pairs:
        for v in {src, src.replace("\\", "/")}:
            text = re.sub(re.escape(v), lambda _m, d=dst: d, text, flags=re.I)
    return short.sub("%USERPROFILE%", text)


def _resolve(rel: str) -> Path:
    p = Path(rel)
    p = p if p.is_absolute() else PROJECT_ROOT / p
    p = p.resolve()
    low = [x.lower() for x in p.parts]
    if "secrets" in low or p.name.lower().startswith(".env") or re.match(r"(client_secret|token).*\.json$", p.name, re.I):
        raise ValueError(f"files with credentials are never shown: {rel}")
    if not p.exists():
        raise FileNotFoundError(f"not found: {p}")
    return p


def _source(scene) -> Path:
    prm = scene.params
    show = prm.get("show")
    rel = prm.get("capture") if show == "terminal" else prm.get("path")
    if show not in ("file", "terminal", "image"):
        raise ValueError(f"scene {scene.index}: unknown show={show!r} (file, terminal or image)")
    if not rel or rel is True:
        raise ValueError(f"scene {scene.index}: show={show} needs {'capture' if show == 'terminal' else 'path'}=")
    return _resolve(rel)


def _sfx_state() -> list:
    out = []
    for name, p in sorted(tp.SFX["files"].items()):
        p = Path(p)
        out.append([name, p.stat().st_size if p.exists() else None, p.stat().st_mtime_ns if p.exists() else None])
    return out


def content_key(scene) -> list:
    """What defines the clip: versions, options, content hash, available fonts and SFX."""
    from .assemble import SCREEN_PANEL_FRAC as PANEL_FRAC
    src = _source(scene)
    h = hashlib.sha1(src.read_bytes()).hexdigest()[:16]
    return ["screens", VERSION, tp.VERSION, PANEL_FRAC, sorted((k, str(v)) for k, v in scene.params.items()), h,
            sorted((k, p.name if p else None) for k, p in font_files().items() if k not in tp.LIBASS_ONLY_FONTS),
            _sfx_state()]


def _ranges(v) -> set[int]:
    out: set[int] = set()
    for part in str(v or "").split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def _list(v) -> list[str]:
    return [x.strip() for x in str(v).split(",") if x.strip()] if v and v is not True else []


def _ease(p: float) -> float:
    """Cubic ease-out."""
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** 3


# ---------------------------------------------------------------- colores por lenguaje (tarjeta clara)
# Cada línea es una lista de estilos por carácter: (color, "r"|"b").

def _style_python(lines: list[str], C: dict) -> list[list]:
    TEXT = (C["body"], "r")
    st = [[TEXT] * len(l) for l in lines]

    def paint(r0, c0, r1, c1, sty):
        for r in range(r0, r1 + 1):
            if r >= len(st):
                break
            a = c0 if r == r0 else 0
            b = c1 if r == r1 else len(st[r])
            for c in range(a, min(b, len(st[r]))):
                st[r][c] = sty

    src = "\n".join(lines) + "\n"
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return st
    prev = None
    for t in toks:
        (r0, c0), (r1, c1) = t.start, t.end
        r0, r1 = r0 - 1, r1 - 1
        if t.type == tokenize.COMMENT:
            paint(r0, c0, r1, c1, (C["muted"], "r"))
        elif t.type in (tokenize.STRING, getattr(tokenize, "FSTRING_START", -1),
                        getattr(tokenize, "FSTRING_MIDDLE", -1), getattr(tokenize, "FSTRING_END", -1)):
            paint(r0, c0, r1, c1, (C["positive"], "r"))
        elif t.type == tokenize.NUMBER:
            paint(r0, c0, r1, c1, (C["cost"], "r"))
        elif t.type == tokenize.NAME:
            if keyword.iskeyword(t.string) or t.string in ("self", "cls"):
                paint(r0, c0, r1, c1, (C["accent"], "r"))
            elif prev is not None and prev.string in ("def", "class"):
                paint(r0, c0, r1, c1, (C["accent2"], "b"))
        if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            prev = t
    return st


_JSON = re.compile(r'"(?:[^"\\]|\\.)*"(?=\s*:)|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\b(?:true|false|null)\b')


def _style_json(lines: list[str], C: dict) -> list[list]:
    st = []
    for l in lines:
        s = [(C["muted"], "r") if ch in "{}[],:" else (C["body"], "r") for ch in l]
        for m in _JSON.finditer(l):
            tok = m.group(0)
            if tok.startswith('"'):
                sty = (C["kpi"], "r") if l[m.end():].lstrip().startswith(":") else (C["positive"], "r")
            elif tok in ("true", "false", "null"):
                sty = (C["accent"], "r")
            else:
                sty = (C["cost"], "r")
            s[m.start():m.end()] = [sty] * (m.end() - m.start())
        st.append(s)
    return st


_MD_TAG = re.compile(r"^\s*\[(SCREEN|EXPLAIN):")


def _style_markdown(lines: list[str], first_line_no: int, all_lines: list[str], C: dict) -> list[list]:
    in_comment = False
    fm = 0
    for l in all_lines[:first_line_no - 1]:
        if l.strip() == "---":
            fm += 1
        if "<!--" in l and "-->" not in l.split("<!--", 1)[1]:
            in_comment = True
        elif "-->" in l:
            in_comment = False
    st = []
    for l in lines:
        s = [(C["body"], "r")] * len(l)
        if in_comment or l.strip().startswith("<!--"):
            s = [(C["muted"], "r")] * len(l)
            if "<!--" in l and "-->" not in l.split("<!--", 1)[1]:
                in_comment = True
            if "-->" in l:
                in_comment = False
        elif l.strip() == "---":
            fm += 1
            s = [(C["muted"], "r")] * len(l)
        elif fm == 1 and ":" in l:
            k = l.index(":")
            s = [(C["kpi"], "r")] * k + [(C["body"], "r")] * (len(l) - k)
        elif l.startswith("#"):
            s = [(C["title"], "b")] * len(l)
        elif _MD_TAG.match(l):
            s = [(C["accent2"], "b")] * len(l)
            if " | " in l:
                k = l.index(" | ")
                end = l.rfind("]")
                for c in range(k, end if end > k else len(l)):
                    s[c] = (C["muted"], "r")
        else:
            for m in re.finditer(r"\{[^{}|]*\|[^{}]*\}", l):
                s[m.start():m.end()] = [(C["positive"], "r")] * (m.end() - m.start())
            for m in re.finditer(r"\*[^*]+\*", l):
                s[m.start():m.end()] = [(C["accent"], "b")] * (m.end() - m.start())
        st.append(s)
    return st


# ---------------------------------------------------------------- dibujo a 2x

class _Draw:
    """Canvas at S×; coordinates in 1080p px."""

    def __init__(self, w: int, h: int, fill):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), fill)
        self.d = ImageDraw.Draw(self.img)

    def rect(self, box, fill=None, r=0, outline=None, width=0):
        x0, y0, x1, y1 = (round(v * S) for v in box)
        if r:
            self.d.rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=round(r * S), fill=fill, outline=outline,
                                     width=round(width * S))
        else:
            self.d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=fill, outline=outline, width=round(width * S))

    def text(self, xy, s, font, fill, anchor="ls"):
        self.d.text((round(xy[0] * S), round(xy[1] * S)), s, font=font, fill=fill, anchor=anchor)

    def down(self) -> Image.Image:
        return self.img.resize((self.w, self.h), Image.LANCZOS)


def _round_mask(w: int, h: int, r: float) -> Image.Image:
    m = Image.new("L", (w * S, h * S), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=round(r * S), fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _ellipsize(s: str, font, max_w: float) -> str:
    while s and font.getlength(s) / S > max_w:
        s = s[:-2] + "…" if len(s) > 2 else ""
    return s


def background(W: int, H: int) -> Image.Image:
    """bg-body background: radial GLOW in the top-right corner, then a GRID px grid in card-border
    at GRID alpha (1 px lines)."""
    C = _colors()
    img = Image.new("RGB", (W, H), C["bg"])
    g = tp.GLOW
    if g["alpha"] > 0:
        # degradado radial con centro en la esquina superior derecha, caída suave (smoothstep)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.hypot(xx - (W - 1), yy) / (g["radius_frac"] * W)
        t = np.clip(1 - r, 0, 1)
        a = (g["alpha"] * t * t * (3 - 2 * t))[..., None]
        base = np.asarray(img, dtype=np.float32)
        glow = np.array(C["glow"], dtype=np.float32)
        noise = np.random.default_rng(0).random((H, W, 1), dtype=np.float32)   # dither fijo: sin bandas
        img = Image.fromarray(np.clip(base * (1 - a) + glow * a + noise, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    step = tp.GRID["px"]
    ox, oy = (W % step) // 2, (H % step) // 2           # cuadrícula centrada
    for x in range(ox, W, step):
        d.line([(x, 0), (x, H)], fill=C["grid"], width=1)
    for y in range(oy, H, step):
        d.line([(0, y), (W, y)], fill=C["grid"], width=1)
    return img


def _text_on(base: Image.Image, box: tuple[int, int, int, int], runs: list[tuple[float, float, str, object, tuple]]):
    """Paints antialiased text over an area of `base` (grid background) using 2x masks:
    runs = [(x, y_baseline, text, font_2x, color)] in absolute 1080p coordinates."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    by_color: dict[tuple, Image.Image] = {}
    for x, y, s, font, color in runs:
        m = by_color.setdefault(color, Image.new("L", (w * S, h * S), 0))
        ImageDraw.Draw(m).text(((x - x0) * S, (y - y0) * S), s, font=font, fill=255, anchor="ls")
    for color, m in by_color.items():
        base.paste(Image.new("RGB", (w, h), color), (x0, y0), m.resize((w, h), Image.LANCZOS))


# ---------------------------------------------------------------- filas de texto monoespaciado

class _Geo:
    def __init__(self, fz: _Fonts, px: int, pad_x: float, pad_y: float, top: float, gutter_digits: int = 0):
        self.px = px
        self.adv = fz("mono_400", px).getlength("M") / S
        self.lh = round(px * LH)
        self.pad_x, self.pad_y, self.top = pad_x, pad_y, top
        self.gutter_digits = gutter_digits
        self.gx = pad_x
        self.tx = pad_x + (gutter_digits + 2) * self.adv if gutter_digits else pad_x

    def row_y(self, i: int) -> float:
        return self.top + self.pad_y + i * self.lh


def _metrics(fz: _Fonts, px: int) -> tuple[float, int]:
    return fz("mono_400", px).getlength("M") / S, round(px * LH)


def _draw_rows(cv: _Draw, rows: list[dict], geo: _Geo, fz: _Fonts, hl: bool, gutter_color, border: float) -> None:
    """rows: {"text", "style", "style_hl", "bg", "bg_hl", "bar", "bar_hl", "words", "num", "num_color(_hl)"}."""
    px, adv, lh = geo.px, geo.adv, geo.lh
    fonts = {"r": fz("mono_400", px), "b": fz("mono_700", px)}
    for i, row in enumerate(rows):
        y = geo.row_y(i)
        bg = (row.get("bg_hl") or row.get("bg")) if hl else row.get("bg")
        bar = (row.get("bar_hl") or row.get("bar")) if hl else row.get("bar")
        if bg:
            cv.rect((border, y, cv.w - border, y + lh), bg)
        if bar:
            cv.rect((border, y, border + 6, y + lh), bar)
        ty = y + lh / 2 + px * 0.36                     # línea base: mayúsculas centradas en la fila
        if geo.gutter_digits and row.get("num") is not None:
            ns = str(row["num"]).rjust(geo.gutter_digits)
            nc = row.get("num_color_hl", row.get("num_color")) if hl else row.get("num_color")
            cv.text((geo.gx, ty), ns, fonts["b" if hl and row.get("num_color_hl") else "r"], nc or gutter_color)
        if hl:
            for a, b, col in row.get("words", []):
                cv.rect((geo.tx + a * adv - 4, y + 3, geo.tx + b * adv + 4, y + lh - 3), col, r=6)
        txt = row["text"]
        sty = row.get("style_hl", row["style"]) if hl else row["style"]
        k = 0
        while k < len(txt):
            j = k
            while j < len(txt) and sty[j] == sty[k]:
                j += 1
            color, w = sty[k]
            cv.text((geo.tx + k * adv, ty), txt[k:j], fonts.get(w, fonts["r"]), color)
            k = j


def _fit(fz: _Fonts, width_text: list[str], avail_h: float, inner_w: float, gutter_digits: int,
         forced: int | None, n_lines_for) -> tuple[int, int, int]:
    """Font size (28–40 px): the largest at which all rows and the widest line fit; failing that,
    the largest that keeps 85 % of the lines whole; otherwise the smallest that fits in height.
    Returns (px, columns, rows)."""
    sizes = [max(MIN_PX, forced)] if forced else list(range(MAX_PX, MIN_PX - 1, -1))
    lens = sorted(len(t) for t in width_text) or [0]
    widest, p85 = lens[-1], lens[int(0.85 * (len(lens) - 1))]
    cands, last = [], None
    for px in sizes:
        adv, lh = _metrics(fz, px)
        cols = int(inner_w / adv) - (gutter_digits + 2 if gutter_digits else 0)
        rows = int(avail_h // lh)
        last = (px, cols, rows)
        if n_lines_for(cols) <= rows:
            cands.append(last)
    if not cands:
        return last
    for need in (widest, p85):
        for c in cands:
            if need <= c[1]:
                return c
    return cands[-1]


def _clip(text: str, style: list, cols: int, dim) -> tuple[str, list]:
    if len(text) <= cols:
        return text, style
    return text[:cols - 1] + "…", style[:cols - 1] + [(dim, "r")]


def _word_spans(text: str, words: list[str]) -> list[tuple[int, int]]:
    spans = []
    for w in words:
        start = 0
        while (i := text.find(w, start)) >= 0:
            spans.append((i, i + len(w)))
            start = i + len(w)
    return spans


def _apply_words(row: dict, words: list[str], bg, fg) -> None:
    spans = [(a, b) for a, b in _word_spans(row["text"], words) if b <= len(row["text"])]
    if not spans:
        return
    row["words"] = [(a, b, bg) for a, b in spans]
    st = list(row.get("style_hl", row["style"]))
    for a, b in spans:
        st[a:b] = [(fg, "b")] * (b - a)
    row["style_hl"] = st


# ---------------------------------------------------------------- escenario: título, área útil, tarjeta

def _heading_runs(text: str) -> list[tuple[str, bool]]:
    """'We *tested* it' -> [('We ', False), ('tested', True), (' it', False)]."""
    out, kw = [], False
    for part in str(text).split("*"):
        if part:
            out.append((part, kw))
        kw = not kw
    return out


class _Stage:
    """Background, optional eyebrow/heading and the usable area for the card (all in 1080p px)."""

    def __init__(self, prm: dict, W: int, H: int, fz: _Fonts, C: dict, band_frac: float):
        self.W, self.H = W, H
        self.bg = background(W, H)
        self.band_y = int(band_frac * H)                 # nada por debajo de esta línea
        self.side = 2 * tp.GRID["px"]                    # 96 px: dos celdas
        self.top = tp.GRID["px"]                         # 48 px: una celda
        self.bottom = self.band_y - 14                   # margen para la sombra de la tarjeta
        self.heading = None
        y = self.top
        runs = []
        eyebrow = prm.get("eyebrow")
        if eyebrow and eyebrow is not True:
            f = fz("heading_500", 30)
            x = self.side
            for ch in str(eyebrow).upper():              # tracking de antetítulo: +0.14 em por letra
                runs.append((x, y + 30, ch, f, C["accent"]))
                x += f.getlength(ch) / S + 30 * 0.14
            y += 30 + 18
        heading = prm.get("heading")
        if heading and heading is not True:
            segs = _heading_runs(str(heading))
            plain = "".join(t for t, _ in segs)
            px = tp.SCALE["title_px"]
            while px > 60 and fz("heading_700", px).getlength(plain) / S > W - 2 * self.side:
                px -= 4
            f = fz("heading_700", px)
            base = y + round(px * 0.80)
            box = (self.side - 8, y - 6, W - self.side + 8, y + round(px * 1.12))
            full = self.bg.crop(box)
            hruns, x = [], self.side
            for t, kw in segs:
                hruns.append((x - box[0], base - box[1], t, f, C["keyword"] if kw else C["title"]))
                x += f.getlength(t) / S
            _text_on(full, (0, 0, full.width, full.height), hruns)
            widths = [0] + [math.ceil(f.getlength(plain[:k]) / S) + (self.side - box[0]) for k in range(1, len(plain) + 1)]
            self.heading = {"text": plain, "box": box, "full": full, "widths": widths, "px": px}
            y = box[3] + 26
        if runs:
            bx = (0, self.top - 8, W, y)
            _text_on(self.bg, bx, runs)
        self.area_top = y
        self.center = self.heading is None               # con título, la tarjeta va pegada debajo


class _Card:
    """Card at (x0, y0) with 1080p layers: base (chrome), full (all content) and hl (with highlights)."""

    def __init__(self, x0: int, y0: int, w: int, h: int):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.mask = _round_mask(w, h, tp.CARD["radius_px"])
        dx, dy, blur, color, alpha = _shadow_spec()
        m = int(math.ceil(blur)) + abs(dy) + abs(dx) + 4
        sh = Image.new("L", (w + 2 * m, h + 2 * m), 0)
        ImageDraw.Draw(sh).rounded_rectangle([m + dx, m + dy, m + dx + w - 1, m + dy + h - 1],
                                             radius=tp.CARD["radius_px"], fill=255)
        # CSS: blur radius r ~ desviación típica r/2
        self.shadow = sh.filter(ImageFilter.GaussianBlur(blur / 2)).point(lambda v, a=alpha: round(v * a))
        self.shadow_rgb = Image.new("RGB", sh.size, color)
        self.shadow_m = m
        self.base = self.full = self.hl = None


def _chrome(card: _Card, C: dict, fz: _Fonts, dark: bool, header_h: int, title: str, right: str,
            lang_pill: str = "") -> _Draw:
    """Card chrome at 2x: background, header, 2 px border. Returns the canvas (to draw on top)."""
    w, h = card.w, card.h
    bw = tp.CARD["border_px"]
    r = tp.CARD["radius_px"]
    cv = _Draw(w, h, C["term_bg"] if dark else C["card_bg"])
    head = C["term_bar"] if dark else C["head_bg"]
    cv.rect((0, 0, w, header_h + r), head, r=r)
    cv.rect((0, header_h, w, header_h + r + 2), C["term_bg"] if dark else C["card_bg"])
    cv.rect((0, header_h, w, header_h + bw), C["t_border"] if dark else C["card_border"])
    cv.rect((0, 0, w, h), None, r=r, outline=C["t_border"] if dark else C["card_border"], width=bw)
    cy = header_h / 2
    if dark:
        for i, key in enumerate(("term_fail", "term_warn", "term_ok")):
            cx = 30 + i * 26
            cv.d.ellipse([round((cx - 7) * S), round((cy - 7) * S), round((cx + 7) * S), round((cy + 7) * S)],
                         fill=C[key])
        f = fz("body_500", 28)
        fr = fz("body_400", 28)
        rw = fr.getlength(right) / S if right else 0
        t = _ellipsize(title, f, w - 2 * (30 + 3 * 26 + 20) - 2 * rw)
        cv.text((w / 2, cy + 1), t, f, C["term_text"], anchor="mm")
        if right:
            cv.text((w - 28 - rw, cy + 1), right, fr, C["term_muted"], anchor="lm")
    else:
        f = fz("body_600", 30)
        fp = fz("body_500", 28)
        pill_w = fp.getlength(lang_pill) / S + 32 if lang_pill else 0
        if lang_pill:
            px1 = w - 24
            cv.rect((px1 - pill_w, cy - 21, px1, cy + 21), C["pill"], r=21)
            cv.text((px1 - pill_w / 2, cy + 1), lang_pill, fp, C["accent"], anchor="mm")
        # cuadro de color + nombre: carpeta en tenue, archivo en color de título
        cv.rect((28, cy - 7, 42, cy + 7), C["accent2"], r=3)
        maxw = w - 60 - 28 - pill_w - 30
        t = _ellipsize(title, f, maxw)
        d, slash, name = t.rpartition("/")
        x = 58
        if slash:
            cv.text((x, cy + 1), d + "/", f, C["muted"], anchor="lm")
            x += f.getlength(d + "/") / S
        cv.text((x, cy + 1), name, f, C["title"], anchor="lm")
        if right:
            fr = fz("body_400", 28)
            cv.text((w - 24 - pill_w - 20 - fr.getlength(right) / S, cy + 1), right, fr, C["muted"], anchor="lm")
    return cv


def _card_box(stage: _Stage, inner_h: float, width: float | None = None, min_h: float = 220) -> tuple[int, int, int, int]:
    avail = stage.bottom - stage.area_top
    h = int(min(avail, max(min_h, inner_h)))
    w = int(width or (stage.W - 2 * stage.side))
    y0 = int(stage.area_top + (max(0, (avail - h) / 2) if stage.center else 0))
    x0 = int((stage.W - w) / 2)
    return x0, y0, w, h


# ---------------------------------------------------------------- paneles

class _Panel:
    """Everything needed to paint any frame: stage, layered card and timeline."""

    def __init__(self):
        self.rows_anim: list[dict] = []    # filas con revelado: {"i", "mode", "t0", "pl", "char_s", "n", "fade"}
        self.geo: _Geo | None = None
        self.card_t0 = 0.0
        self.hl_t = None
        self.cursor = None                 # {"row", "col", "blink_from", ...}
        self.events: list[tuple[float, str]] = []
        self.image = None
        self.info: dict = {}


def _render_file(scene, src: Path, stage: _Stage, fz: _Fonts, C: dict) -> _Panel:
    prm = scene.params
    raw = src.read_text(encoding="utf-8", errors="replace").expandtabs(4)
    all_lines = [redact(l) for l in raw.splitlines()]
    total = len(all_lines)
    if prm.get("lines"):
        a, _, b = str(prm["lines"]).partition("-")
        start, end = int(a), int(b or a)
    else:
        start = 1
        if prm.get("find"):
            for anchor in str(prm["find"]).split(">"):
                anchor = anchor.strip()
                hit = next((i for i in range(start, total + 1) if anchor in all_lines[i - 1]), None)
                if hit is None:
                    raise ValueError(f"scene {scene.index}: find={prm['find']!r}: {anchor!r} not found in {src.name}")
                start = hit
        start = max(1, start + int(prm.get("skip", 0)))
        end = start + int(prm["n"]) - 1 if prm.get("n") else total
    end = min(end, total)
    digits = len(str(end))
    forced = int(prm["size"]) if prm.get("size") else None
    header_h, pad_x, pad_y = 64, 30, 20
    inner_w = stage.W - 2 * stage.side - 2 * pad_x
    avail_h = stage.bottom - stage.area_top - header_h - 2 * pad_y
    want = all_lines[start - 1:end]
    px, cols, rows_fit = _fit(fz, want, avail_h, inner_w, digits, forced, lambda c: len(want))
    cropped = max(0, end - start + 1 - rows_fit)
    end = min(end, start + rows_fit - 1)
    ext = src.suffix.lower()
    shown = all_lines[start - 1:end]
    if ext == ".py":
        styles, lang = _style_python(all_lines, C)[start - 1:end], "Python"
    elif ext == ".json":
        styles, lang = _style_json(shown, C), "JSON"
    elif ext in (".md", ".markdown"):
        styles, lang = _style_markdown(shown, start, all_lines, C), "Markdown"
    else:
        styles, lang = [[(C["body"], "r")] * len(l) for l in shown], ext.lstrip(".").upper() or "Text"
    hl = _ranges(prm.get("hl"))
    marks = _list(prm.get("mark"))
    words = _list(prm.get("highlight"))
    rows = []
    for k, (t, s) in enumerate(zip(shown, styles)):
        no = start + k
        t, s = _clip(t, list(s), cols, C["muted"])
        lit = no in hl or any(m in t for m in marks)
        row = {"text": t, "style": s, "num": no, "num_color": C["gutter"]}
        if lit:
            row.update(bg_hl=C["hl_line"], bar_hl=C["accent"], num_color_hl=C["accent"])
        _apply_words(row, words, C["hl_word"], C["accent"])
        rows.append(row)
    adv, lh = _metrics(fz, px)
    x0, y0, w, h = _card_box(stage, header_h + 2 * pad_y + len(rows) * lh)
    card = _Card(x0, y0, w, h)
    rel = src.relative_to(PROJECT_ROOT).as_posix() if src.is_relative_to(PROJECT_ROOT) else src.name
    geo = _Geo(fz, px, pad_x, pad_y, header_h)
    geo.gutter_digits, geo.gx = digits, pad_x
    geo.tx = pad_x + (digits + 2) * geo.adv
    title = str(prm.get("title") or rel)
    pill = f"{lang} · {start}–{end}"
    cv = _chrome(card, C, fz, False, header_h, title, "", pill)
    base = cv.img.copy()
    _draw_rows(cv, rows, geo, fz, False, C["gutter"], tp.CARD["border_px"])
    card.full = cv.down()
    card.base = card.full
    has_hl = any(r.get("bg_hl") or r.get("words") for r in rows)
    if has_hl:
        cv.img = base
        cv.d = ImageDraw.Draw(cv.img)
        _draw_rows(cv, rows, geo, fz, True, C["gutter"], tp.CARD["border_px"])
        card.hl = cv.down()
    pn = _Panel()
    pn.card, pn.geo = card, geo
    pn.hl_t = (ENTER_S + HL_DELAY_S) if has_hl else None
    pn.info = {"font_px": px, "lines": [start, end], "cropped_lines": cropped, "language": lang}
    return pn


_STATUS_LEAD = re.compile(r"^(\s*)(OK|WARN|FAIL)\b")
_STATUS_SUM = re.compile(r"\b\d+ (OK|WARN|FAIL)\b")
_COST = re.compile(r"(?<![\w$])\$\s?\d[\d.,]*")


def _wrap_out(t: str, cols: int) -> list[str]:
    out = []
    while len(t) > cols:
        cut = t.rfind(", ", 0, cols)
        cut = cut + 2 if cut > cols // 3 else cols
        out.append(t[:cut].rstrip())
        t = " " + t[cut:]
    return out + [t]


def _wrap_cmd(t: str, cols: int) -> list[str]:
    out = []
    while len(t) > cols:
        cut = t.rfind(" ", 0, cols)
        cut = cut + 1 if cut > cols // 2 else cols
        out.append(t[:cut])
        t = t[cut:]
    return out + [t]


def _render_terminal(scene, src: Path, stage: _Stage, fz: _Fonts, C: dict, duration_s: float) -> _Panel:
    prm = scene.params
    raw = [redact(l.expandtabs(4)) for l in src.read_text(encoding="utf-8", errors="replace").splitlines()]
    nums = list(range(1, len(raw) + 1))
    if prm.get("lines"):
        keep = _ranges(prm["lines"])
        pairs = [(n, l) for n, l in zip(nums, raw) if n in keep]
    else:
        pairs = list(zip(nums, raw))
    while pairs and not pairs[-1][1].strip():
        pairs.pop()
    prompt = str(prm.get("prompt") or ">")
    wrap = bool(prm.get("wrap"))
    forced = int(prm["size"]) if prm.get("size") else None
    header_h, pad_x, pad_y = 56, 30, 20
    inner_w = stage.W - 2 * stage.side - 2 * pad_x
    avail_h = stage.bottom - stage.area_top - header_h - 2 * pad_y

    def logical(compact: bool):
        items = []
        for n, l in pairs:
            if compact and not l.strip():
                continue
            if l.startswith("$ "):
                items.append(("cmd", n, f"{prompt} {l[2:]}"))
            elif l.startswith("#!"):
                items.append(("note", n, "# " + l[2:].strip()))
            else:
                items.append(("out", n, l))
        while items and items[0][0] == "out" and not items[0][2].strip():
            items.pop(0)
        return items

    def expand(items, cols):
        rows = []
        for kind, n, t in items:
            parts = _wrap_cmd(t, cols) if kind == "cmd" else (_wrap_out(t, cols) if wrap and kind == "out" else [t])
            rows += [(kind, n, p, j) for j, p in enumerate(parts)]
        return rows

    items = logical(False)
    clipped = lambda its: [t for k, _, t in its if k == "note" or (k == "out" and not wrap)]  # noqa: E731
    px, cols, rows_fit = _fit(fz, clipped(items), avail_h, inner_w, 0, forced, lambda c: len(expand(items, c)))
    compacted = False
    if len(expand(items, cols)) > rows_fit:          # sin espacio: se quitan las líneas en blanco
        items, compacted = logical(True), True
        px, cols, rows_fit = _fit(fz, clipped(items), avail_h, inner_w, 0, forced, lambda c: len(expand(items, c)))
    lines = expand(items, cols)
    cropped = max(0, len(lines) - rows_fit)
    lines = lines[:rows_fit]
    end_prompt = len(lines) < rows_fit               # sitio para un prompt final con cursor
    hl = _ranges(prm.get("hl"))
    marks = _list(prm.get("mark"))
    words = _list(prm.get("highlight"))
    rows = []
    pl = len(prompt) + 1
    for kind, n, t, j in lines:
        t_full = t
        if kind == "cmd":
            p = pl if j == 0 else 0
            style = [(C["term_prompt"], "b")] * p + [(C["term_text"], "b")] * (len(t) - p)
        elif kind == "note":
            style = [(C["term_muted"], "r")] * len(t)
        else:
            style = [(C["term_text"], "r")] * len(t)
            m = _STATUS_LEAD.match(t)
            status = {"OK": C["term_ok"], "WARN": C["term_warn"], "FAIL": C["term_fail"]}
            if m:
                style[m.start(2):m.end(2)] = [(status[m.group(2)], "b")] * (m.end(2) - m.start(2))
            for m in _STATUS_SUM.finditer(t):
                style[m.start():m.end()] = [(status[m.group(1)], "b")] * (m.end() - m.start())
            for m in _COST.finditer(t):
                style[m.start():m.end()] = [(C["term_warn"], "b")] * (m.end() - m.start())
        t, style = _clip(t, style, cols, C["term_muted"])
        fail = kind == "out" and bool(re.match(r"^\s*FAIL\b", t_full))
        lit = n in hl or any(mk in t_full for mk in marks)
        row = {"text": t, "style": style, "kind": kind, "j": j,
               "bg": C["t_fail_line"] if fail else None, "bar": C["term_fail"] if fail else None}
        if lit:
            row.update(bg_hl=C["t_hl_line"], bar_hl=C["term_prompt"])
        _apply_words(row, words, C["t_hl_word"], C["term_text"])
        rows.append(row)
    if end_prompt:
        rows.append({"text": prompt, "style": [(C["term_prompt"], "b")] * len(prompt), "kind": "end", "j": 0})
    adv, lh = _metrics(fz, px)
    x0, y0, w, h = _card_box(stage, header_h + 2 * pad_y + len(rows) * lh)
    card = _Card(x0, y0, w, h)
    geo = _Geo(fz, px, pad_x, pad_y, header_h)
    title = str(prm.get("title") or "PowerShell")
    cv = _chrome(card, C, fz, True, header_h, title, "tbl · " + PROJECT_ROOT.name)
    card.base = cv.down()
    _draw_rows(cv, rows, geo, fz, False, C["term_muted"], tp.CARD["border_px"])
    card.full = cv.down()
    has_hl = any(r.get("bg_hl") or r.get("words") for r in rows)
    if has_hl:
        cv = _chrome(card, C, fz, True, header_h, title, "tbl · " + PROJECT_ROOT.name)
        _draw_rows(cv, rows, geo, fz, True, C["term_muted"], tp.CARD["border_px"])
        card.hl = cv.down()

    # ---- línea de tiempo: notas iniciales con la tarjeta, prompt visible, comando a máquina, salida escalonada
    pn = _Panel()
    pn.card, pn.geo = card, geo
    first_cmd = next((i for i, r in enumerate(rows) if r["kind"] == "cmd"), None)
    n_chars = sum(len(r["text"]) - (pl if r["j"] == 0 else 0) for r in rows if r["kind"] == "cmd")
    n_out = sum(1 for i, r in enumerate(rows) if r["kind"] in ("out", "note") and (first_cmd is None or i > first_cmd))
    n_cmds = sum(1 for r in rows if r["kind"] == "cmd" and r["j"] == 0)
    t_start = ENTER_S + 0.12 if first_cmd is not None else ENTER_S * 0.6
    deadline = max(t_start + 0.6, min(0.62 * duration_s, duration_s - 1.3))
    natural = n_chars * tp.MOTION["command_char_s"] + n_out * STAGGER_S
    pauses = n_cmds * ENTER_PAUSE_S
    k = min(1.0, max(0.05, deadline - t_start - pauses) / natural) if natural > 0 else 1.0
    char_s, stag = tp.MOTION["command_char_s"] * k, STAGGER_S * k
    t = t_start
    anim = []
    for i, r in enumerate(rows):
        if r["kind"] == "end":
            continue
        if first_cmd is not None and i < first_cmd:
            continue                                   # notas previas: llegan con la tarjeta
        if r["kind"] == "cmd":
            p = pl if r["j"] == 0 else 0
            n = len(r["text"]) - p
            anim.append({"i": i, "mode": "type", "t_prompt": 0.0 if i == first_cmd else t, "t0": t, "pl": p,
                         "n": n, "char_s": char_s})
            t += n * char_s
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            if not (nxt and nxt["kind"] == "cmd" and nxt["j"] > 0):
                pn.events.append((t, tp.SFX["rules"]["typewriter_end"]))
                t += ENTER_PAUSE_S
        else:
            anim.append({"i": i, "mode": "fade", "t0": t})
            t += stag
    reveal_end = (t - stag + LINE_FADE_S) if n_out else t
    if end_prompt:
        anim.append({"i": len(rows) - 1, "mode": "fade", "t0": reveal_end - LINE_FADE_S * 0.5})
    pn.rows_anim = anim
    # cursor: tras el prompt antes de escribir, al final de lo escrito mientras escribe, y en el prompt final
    pn.cursor = {"rows": rows, "pl": pl, "end_row": len(rows) - 1 if end_prompt else None,
                 "end_t": reveal_end, "first_cmd": first_cmd}
    if has_hl:
        pn.hl_t = min(max(reveal_end + HL_DELAY_S, ENTER_S + HL_DELAY_S), max(reveal_end, duration_s - 1.0))
    pn.info = {"font_px": px, "rows": len(rows), "cropped_rows": cropped, "blank_lines_removed": compacted,
               "typing_ms_per_char": round(char_s * 1000, 1), "stagger_ms": round(stag * 1000, 1),
               "reveal_end_s": round(reveal_end, 2)}
    return pn


def _render_image(scene, src: Path, stage: _Stage, fz: _Fonts, C: dict) -> _Panel:
    prm = scene.params
    im = Image.open(src).convert("RGB")
    header_h, pad = 64, 16
    avail_w = stage.W - 2 * stage.side - 2 * pad
    avail_h = stage.bottom - stage.area_top - header_h - 2 * pad
    k = min(avail_w / im.width, avail_h / im.height)
    iw, ih = int(im.width * k), int(im.height * k)
    x0, y0, w, h = _card_box(stage, header_h + ih + 2 * pad, iw + 2 * pad)
    card = _Card(x0, y0, w, h)
    cv = _chrome(card, C, fz, False, header_h, str(prm.get("title") or src.name), "", f"{im.width}×{im.height}")
    ix, iy = pad, header_h + pad
    cv.rect((ix - 2, iy - 2, ix + iw + 2, iy + ih + 2), C["card_border"], r=10)
    card.full = cv.down()
    card.base = card.full
    pn = _Panel()
    pn.card = card
    # fuente reducida una vez (lanczos) al tamaño del zoom máximo: cada frame es un recorte casi 1:1
    big = im.resize((math.ceil(iw * IMG_ZOOM), math.ceil(ih * IMG_ZOOM)), Image.LANCZOS)
    pn.image = {"src": big, "box": (ix, iy, iw, ih), "mask": _round_mask(iw, ih, 8)}
    pn.info = {"image": [im.width, im.height], "shown_px": [iw, ih], "zoom": f"1.00→{IMG_ZOOM}"}
    return pn


# ---------------------------------------------------------------- animación

class _Animator:
    def __init__(self, stage: _Stage, pn: _Panel, duration_s: float):
        self.stage, self.pn, self.D = stage, pn, duration_s
        c = pn.card
        self.card = c
        # escenario con la sombra de la tarjeta en su sitio final
        self.stage_img = stage.bg.copy()
        m = c.shadow_m
        self.stage_img.paste(c.shadow_rgb, (c.x0 - m, c.y0 - m), c.shadow)
        self.band = stage.bg.crop((0, stage.band_y, stage.W, stage.H))
        self.last_sig, self.last_bytes = None, None
        h = stage.heading
        self.h_char = tp.MOTION["title_char_s"]
        self.h_t0 = 0.05
        self.h_end = self.h_t0 + len(h["text"]) * self.h_char if h else 0.0
        pn.card_t0 = self.h_end + 0.05 if h else 0.0
        # los tiempos internos del panel son relativos a la entrada de la tarjeta
        ev = [(pn.card_t0, tp.SFX["rules"]["card_enter"])]
        if h:
            ev.append((self.h_end, tp.SFX["rules"]["typewriter_end"]))
        pn.events = sorted(ev + [(t + pn.card_t0, n) for t, n in pn.events])

    def _cursor(self, ct: float):
        cur = self.pn.cursor
        if not cur:
            return None
        blink = tp.MOTION["cursor_blink_s"]
        on = lambda t0: ((ct - t0) % (2 * blink)) < blink  # noqa: E731
        typed = [a for a in self.pn.rows_anim if a["mode"] == "type"]
        if typed and ct < typed[0]["t0"]:
            a = typed[0]
            return (a["i"], a["pl"]) if on(0.0) else None
        for a in typed:
            end = a["t0"] + a["n"] * a["char_s"]
            if a["t0"] <= ct < end + 0.08:
                return a["i"], a["pl"] + min(a["n"], int((ct - a["t0"]) / a["char_s"]) + 1)
        if cur["end_row"] is not None and ct >= cur["end_t"]:
            return (cur["end_row"], cur["pl"]) if on(cur["end_t"]) else None
        return None

    def _state(self, t: float):
        pn = self.pn
        ct = t - pn.card_t0
        a = _ease(ct / ENTER_S) if ct >= 0 else 0.0
        dy = round(SLIDE_PX * (1 - a))
        ai = round(a * 255)
        h = self.stage.heading
        hk = 0
        if h and t >= self.h_t0:
            hk = min(len(h["text"]), int((t - self.h_t0) / self.h_char) + 1)
        rev = []
        for an in pn.rows_anim:
            if an["mode"] == "type":
                pv = an["pl"] if ct >= an["t_prompt"] else 0
                n = 0 if ct < an["t0"] else min(an["n"], int((ct - an["t0"]) / an["char_s"]) + 1)
                rev.append((pv, n))
            else:
                rev.append(round(255 * _ease((ct - an["t0"]) / LINE_FADE_S)) if ct >= an["t0"] else 0)
        hl = round(255 * _ease((ct - pn.hl_t) / HL_FADE_S)) if pn.hl_t is not None and ct >= pn.hl_t else 0
        cur = self._cursor(ct) if ct >= 0 else None
        zoom = None
        if pn.image:
            zoom = round(1 + (IMG_ZOOM - 1) * min(1.0, max(0.0, t / max(self.D, 1e-3))), 5)
        return (ai, dy, hk, tuple(rev), hl, cur, zoom)

    def frame(self, t: float) -> bytes:
        sig = self._state(t)
        if sig == self.last_sig:
            return self.last_bytes
        zoom = sig[-1]
        if sig[:-1] != getattr(self, "base_sig", None):      # el cuadro sin la imagen con zoom
            self.base_sig, self.base_img = sig[:-1], self._compose(*sig[:-1])
        out = self.base_img
        if zoom is not None:                                  # solo la imagen cambia en cada frame
            pn, c = self.pn, self.card
            im, (ix, iy, iw, ih), m = pn.image["src"], pn.image["box"], pn.image["mask"]
            # recorte centrado de la imagen original con coordenadas fraccionarias (acercamiento subpíxel)
            cw, ch = im.width / zoom, im.height / zoom
            bx0, by0 = (im.width - cw) / 2, (im.height - ch) / 2
            region = im.resize((iw, ih), Image.BICUBIC, box=(bx0, by0, bx0 + cw, by0 + ch))
            ai, dy = sig[0], sig[1]
            if ai > 0:
                out = out.copy()
                k = ai / 255
                out.paste(region, (c.x0 + ix, c.y0 + dy + iy), m if ai >= 255 else m.point(lambda v: round(v * k)))
                if dy:
                    out.paste(self.band, (0, self.stage.band_y))
        self.last_sig, self.last_bytes = sig, out.tobytes()
        return self.last_bytes

    def _compose(self, ai, dy, hk, rev, hl, cur) -> Image.Image:
        pn, c, g = self.pn, self.card, self.pn.geo
        # contenido de la tarjeta
        if pn.rows_anim:
            mask = Image.new("L", (c.w, c.h), 0)
            d = ImageDraw.Draw(mask)
            rows_hidden = {an["i"] for an in pn.rows_anim}
            # filas sin animación (notas previas a la primera orden): siempre visibles
            for i in range(len(pn.cursor["rows"]) if pn.cursor else 0):
                if i not in rows_hidden:
                    y = g.row_y(i)
                    d.rectangle([0, int(y), c.w - 1, int(y + g.lh) - 1], fill=255)
            for an, v in zip(pn.rows_anim, rev):
                y = g.row_y(an["i"])
                if an["mode"] == "type":
                    pv, n = v
                    cols = (pv + n) if n else pv
                    if cols:
                        d.rectangle([0, int(y), math.ceil(g.tx + cols * g.adv) + 1, int(y + g.lh) - 1], fill=255)
                elif v:
                    d.rectangle([0, int(y), c.w - 1, int(y + g.lh) - 1], fill=v)
            img = Image.composite(c.full, c.base, mask)
        else:
            img = c.full.copy()
        if hl and c.hl is not None:
            img = Image.blend(img, c.hl, hl / 255)
        if cur is not None:
            row, col = cur
            y = g.row_y(row)
            x = g.tx + col * g.adv
            ImageDraw.Draw(img).rectangle([round(x) + 1, round(y + g.lh * 0.14), round(x + g.adv * 0.92),
                                           round(y + g.lh * 0.86)], fill=_rgb(tp.palette()["term_text"]))
        # composición en el cuadro
        if ai >= 255 and dy == 0:
            out = self.stage_img.copy()
            out.paste(img, (c.x0, c.y0), c.mask)
        else:
            out = self.stage.bg.copy()
            if ai > 0:
                k = ai / 255
                m = c.shadow_m
                out.paste(c.shadow_rgb, (c.x0 - m, c.y0 + dy - m), c.shadow.point(lambda v: round(v * k)))
                out.paste(img, (c.x0, c.y0 + dy), c.mask.point(lambda v: round(v * k)))
                out.paste(self.band, (0, self.stage.band_y))          # nada bajo la franja de subtítulos
        h = self.stage.heading
        if h and hk:
            bx = h["box"]
            out.paste(h["full"].crop((0, 0, min(h["full"].width, h["widths"][hk]), h["full"].height)), (bx[0], bx[1]))
        return out


def _build(scene, W: int, H: int, duration_s: float) -> tuple[_Stage, _Panel, Path]:
    from .assemble import SCREEN_PANEL_FRAC as PANEL_FRAC
    src = _source(scene)
    fz, C = _Fonts(), _colors()
    stage = _Stage(scene.params, W, H, fz, C, PANEL_FRAC)
    show = scene.params["show"]
    if show == "file":
        pn = _render_file(scene, src, stage, fz, C)
    elif show == "terminal":
        h = stage.heading                         # con título, la tarjeta entra cuando termina de escribirse
        card_d = duration_s - (0.10 + len(h["text"]) * tp.MOTION["title_char_s"] if h else 0.0)
        pn = _render_terminal(scene, src, stage, fz, C, card_d)
    else:
        pn = _render_image(scene, src, stage, fz, C)
    return stage, pn, src


def render_clip(scene, out_mp4: Path, W: int, H: int, fps: int, frames: int) -> dict:
    """Animated panel clip: PIL frames piped to FFmpeg (libx264, COLOR_VF/COLOR_ARGS) + SFX track
    (sfx.place; silent if there are no events). Exactly `frames` frames. Returns data for the manifest."""
    from . import sfx
    from .assemble import COLOR_ARGS, COLOR_VF, add_clip_audio
    t0 = time.perf_counter()
    D = frames / fps
    stage, pn, src = _build(scene, W, H, D)
    anim = _Animator(stage, pn, D)
    t_build = time.perf_counter() - t0
    # SFX: los que falten en assets/sfx/ se omiten (y se avisa); la pista existe siempre
    missing = sorted({n for _, n in pn.events if not Path(tp.SFX["files"][n]).exists()})
    events = [(round(t, 3), n) for t, n in pn.events if n not in missing and t < D]
    wav = out_mp4.with_name(out_mp4.stem + ".sfx.wav")
    sfx.place(events, D, wav)
    tmp = out_mp4.with_name(out_mp4.stem + ".writing.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", "-vf", COLOR_VF, "-frames:v", str(frames),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", *COLOR_ARGS, "-r", str(fps), str(tmp)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_NOWIN)
    t_draw = 0.0
    try:
        for i in range(frames):
            a = time.perf_counter()
            buf = anim.frame(i / fps)
            t_draw += time.perf_counter() - a
            p.stdin.write(buf)
        p.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    err = p.stderr.read().decode("utf-8", "replace")
    if p.wait() != 0:
        wav.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed ({p.returncode}) in the panel of scene {scene.index}: {err.strip()[-600:]}")
    try:
        add_clip_audio(tmp, frames, fps, wav)       # pista SFX a ganancia unitaria, duración exacta del clip
    finally:
        wav.unlink(missing_ok=True)
    os.replace(tmp, out_mp4)
    rel = src.relative_to(PROJECT_ROOT).as_posix() if src.is_relative_to(PROJECT_ROOT) else str(src)
    warnings = []
    if fonts_missing():
        warnings.append(f"theme fonts missing in assets/fonts/ ({', '.join(fonts_missing())}): Windows fonts were used")
    if missing:
        warnings.append(f"SFX missing in assets/sfx/ ({', '.join(missing)}): track without those effects")
    return {"show": scene.params["show"], "source": rel, **pn.info, "theme": f"{tp.NAME} v{tp.VERSION}",
            "card_enter_s": round(pn.card_t0, 2), "sfx_events": events, "warnings": warnings,
            "timing_s": {"build": round(t_build, 2), "draw": round(t_draw, 2),
                         "total": round(time.perf_counter() - t0, 2)}}


def render_png(scene, out_png: Path, W: int, H: int, t: float | None = None, duration_s: float = 4.0) -> dict:
    """One frame of the panel (by default the final state) as PNG: for reviews and contact sheets."""
    stage, pn, src = _build(scene, W, H, duration_s)
    anim = _Animator(stage, pn, duration_s)
    buf = anim.frame(duration_s - 1e-3 if t is None else t)
    Image.frombytes("RGB", (W, H), buf).save(out_png)
    return {"show": scene.params["show"], **pn.info}


def placeholder_png(label: str, out_png: Path, W: int, H: int, zmax: float, band_frac: float) -> None:
    """Placeholder for a SCREEN without show/src, in the paper theme, at 2x (assemble.screen_image; then
    Ken Burns): grid background and a card with the scene description. At the maximum zoom `zmax`
    (centered) everything stays above band_frac·H."""
    fz, C = _Fonts(), _colors()
    bottom = int(H / 2 + (band_frac * H - 14 - H / 2) / zmax)
    top = int(H / 2 - (H / 2 - tp.GRID["px"]) / zmax) + 8
    side = 2 * tp.GRID["px"] + 24
    bg = background(W, H)
    card = _Card(side, top, W - 2 * side, bottom - top)
    cv = _Draw(card.w, card.h, C["card_bg"])
    cv.rect((0, 0, card.w, card.h), None, r=tp.CARD["radius_px"], outline=C["card_border"], width=tp.CARD["border_px"])
    f_eb, f_body = fz("heading_500", 30), fz("body_500", 44)
    cv.text((56, 56 + 30), " ".join("SCREEN"), f_eb, C["accent"])
    words, line, y = str(label[0].upper() + label[1:]).split(), "", 56 + 30 + 70
    lines = []
    for wd in words:
        if f_body.getlength((line + " " + wd).strip()) / S > card.w - 112:
            lines.append(line)
            line = wd
        else:
            line = (line + " " + wd).strip()
    lines.append(line)
    for l in lines[:6]:
        cv.text((56, y), l, f_body, C["body"])
        y += 62
    cv.text((56, card.h - 48), "placeholder · screen recording pending", fz("body_400", 30), C["muted"])
    img = bg.copy()
    m = card.shadow_m
    img.paste(card.shadow_rgb, (card.x0 - m, card.y0 - m), card.shadow)
    img.paste(cv.down(), (card.x0, card.y0), card.mask)
    img.resize((W * S, H * S), Image.LANCZOS).save(out_png)

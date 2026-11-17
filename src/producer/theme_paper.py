"""The Producer's "paper" visual theme: DM identity (dm-design-system) adapted to 1080p video.

The ONLY source of the video's colors, fonts, scales, motion and SFX levels. No other module
(not even explainroo's scenes.js) may hard-code colors: they all come from here.

Source: assets/brand/tokens.json (copy of dm-design-system, see assets/brand/SOURCE.md).
- Video on a LIGHT background: tokens.color.themes.light.
- DARK simulated terminal: surface and text from tokens.color.themes.dark (prompt in its accent2).
Note: in the light theme accent2 is #0891B2 (#06B6D4 is the dark theme's accent2, used by the terminal).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import PROJECT_ROOT

VERSION = 3                                    # subir al cambiar tokens, escalas o fuentes (invalida cachés)
# v2: look de explainroo (explainroo_look), video.json (explainroo_video) y THEME de scenes.js (scenes_theme)
NAME = "paper"
BRAND_DIR = PROJECT_ROOT / "assets" / "brand"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
SFX_DIR = PROJECT_ROOT / "assets" / "sfx"


@lru_cache(maxsize=1)
def tokens() -> dict:
    return json.loads((BRAND_DIR / "tokens.json").read_text(encoding="utf-8"))


def light() -> dict:
    return tokens()["color"]["themes"]["light"]


def dark() -> dict:
    return tokens()["color"]["themes"]["dark"]


# ------------------------------------------------------------------ conversión de colores

def rgba(value: str) -> tuple[int, int, int, float]:
    """'#2563EB' | 'rgba(15,23,42,0.10)' -> (r, g, b, a)."""
    v = value.strip()
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a
    m = re.match(r"rgba?\(([^)]*)\)", v)
    if not m:
        raise ValueError(f"unrecognized color: {value}")
    parts = [p.strip() for p in m.group(1).split(",")]
    r, g, b = (int(float(p)) for p in parts[:3])
    return r, g, b, float(parts[3]) if len(parts) > 3 else 1.0


def over(fg: str, bg: str, alpha_scale: float = 1.0) -> tuple[int, int, int]:
    """Opaque color of `fg` (its alpha × alpha_scale) composited over `bg`."""
    r, g, b, a = rgba(fg)
    R, G, B, _ = rgba(bg)
    a *= alpha_scale
    return round(r * a + R * (1 - a)), round(g * a + G * (1 - a)), round(b * a + B * (1 - a))


def hex_of(rgb: tuple[int, ...]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def ass_color(value: str | tuple[int, ...], alpha: float = 1.0) -> str:
    """Color for ASS/libass: &HAABBGGRR (AA = transparency, 00 = opaque)."""
    r, g, b = (rgba(value)[:3] if isinstance(value, str) else value[:3])
    return f"&H{round((1 - alpha) * 255):02X}{b:02X}{g:02X}{r:02X}"


# ------------------------------------------------------------------ paleta por función

def palette() -> dict:
    L, D = light(), dark()
    bg = L["bgBody"]
    return {
        "bg": bg,                                           # fondo de todo el video
        "grid": hex_of(over(L["cardBorder"], bg, GRID["alpha"])),   # cuadrícula: card-border al 45 %
        "glow": GLOW["color"],                              # brillo radial arriba a la derecha (derivado, no es token)
        "surface": L["surface1"],
        "card_bg": L["cardBg"],
        "card_border": hex_of(over(L["cardBorder"], L["cardBg"])),  # opaco sobre la tarjeta
        "title": L["textTitle"],
        "body": L["textBody"],
        "muted": L["textMuted"],
        "keyword": L["accent"],                             # una palabra clave por frase
        "accent": L["accent"],
        "accent2": L["accent2"],
        "cost": L["accent3"],                               # cifras de costo y advertencias
        "warning": L["accent3"],
        "positive": L["positive"],
        "negative": L["negative"],
        "kpi": L["kpi"],
        # terminal simulada: tema OSCURO
        "term_bg": D["surface1"],
        "term_bar": D["surface2"],
        "term_text": D["textBody"],
        "term_muted": D["textMuted"],
        "term_prompt": D["accent2"],
        "term_ok": D["positive"],
        "term_fail": D["negative"],
        "term_warn": D["accent3"],
        "term_hl": D["accent"],
    }


GRID = {"px": 48, "alpha": 0.45}                     # cuadrícula del fondo: 48 px, card-border al 45 %
# Brillo: degradado radial azul claro en la esquina superior derecha, al 20 % en el centro y a 0 en el borde.
# Color derivado aprobado por el dueño (no está en dm-design-system); radio como fracción del ancho.
GLOW = {"color": "#DCE6FF", "alpha": 0.20, "radius_frac": 0.60}
CARD = {"radius_px": int(re.sub(r"\D", "", tokens()["layout"]["radius"]["panel"]) or 12),
        "border_px": 2, "shadow": tokens()["layout"]["panelShadow"]["light"]}

# ------------------------------------------------------------------ tipografía (px a 1080p)

FONT_FAMILIES = {
    "heading": tokens()["typography"]["heading"]["family"],   # Space Grotesk
    "body": tokens()["typography"]["body"]["family"],         # Inter
    "mono": tokens()["typography"]["mono"]["family"],         # JetBrains Mono
}
SCALE = {
    "title_px": 96, "title_weight": 700,          # Space Grotesk 700
    "subtitle_px": 72, "subtitle_weight": 600,    # (THEME.size.subtitle de scenes.js; = callout_px)
    # Tamaños ASS: libass escala la fuente para que winAscent + winDescent = tamaño (Inter: em = 0,699 × tamaño)
    "callout_px": 72, "callout_weight": 600,      # long-form: callout de 3–6 palabras en SCREEN, Inter 600
    "karaoke_px": 110, "karaoke_weight": 700,     # Shorts: subtítulo karaoke palabra por palabra, Inter 700
    "body_px": 44, "body_weight": 500,
    "mono_px": 40, "mono_weight": 400,            # JetBrains Mono (cifras, código, terminal)
    "small_px": 32,
    "figure_scale": 1.3,          # tarjetas de cifras (marcador, memoria, costo): ×1,3, aprobado por el dueño
}
# archivos de fuente (estáticos, OFL) en assets/fonts/: los crea scripts de setup; nombre -> archivo
FONT_FILES = {
    "heading_700": FONTS_DIR / "SpaceGrotesk-Bold.ttf",
    "heading_500": FONTS_DIR / "SpaceGrotesk-Medium.ttf",
    "body_400": FONTS_DIR / "Inter-Regular.ttf",
    "body_500": FONTS_DIR / "Inter-Medium.ttf",
    "body_600": FONTS_DIR / "Inter-SemiBold.ttf",
    "body_700": FONTS_DIR / "Inter-Bold.ttf",        # solo libass (karaoke de Shorts)
    "mono_400": FONTS_DIR / "JetBrainsMono-Regular.ttf",
    "mono_700": FONTS_DIR / "JetBrainsMono-Bold.ttf",
}
# Fuentes que solo usa libass: no se copian al proyecto de explainroo (así look_hash, la clave de caché de
# las EXPLAIN, no cambia al añadirlas).
LIBASS_ONLY_FONTS = frozenset({"body_700"})
# familia (name ID 1) de cada archivo estático: es lo que se pide en ASS/libass (Fontname) con Bold=0.
# libass solo empareja por ID 1 / nombre completo: "Inter" + Bold=600 elige Inter-Regular y lo engorda
# (comprobado con -v debug, 2026-11-16); "Inter SemiBold" + Bold=0 elige Inter-SemiBold.ttf sin engordar.
FONT_FACES = {
    "heading_700": "Space Grotesk",          # ID 2 = Bold (estilo RIBBI)
    "heading_500": "Space Grotesk Medium",
    "body_400": "Inter",
    "body_500": "Inter Medium",
    "body_600": "Inter SemiBold",
    "body_700": "Inter",                     # ID 2 = Bold (RIBBI): en ASS, Fontname "Inter" con Bold=1
    "mono_400": "JetBrains Mono",
    "mono_700": "JetBrains Mono",            # ID 2 = Bold
}
# archivos cuyo name ID 2 es "Bold" (RIBBI): en ASS se piden con su familia y Bold=1
FONT_ASS_BOLD = frozenset({"heading_700", "body_700", "mono_700"})

# ------------------------------------------------------------------ movimiento y sonido

MOTION = {
    "ease": "out",
    "enter_min_s": 0.25, "enter_max_s": 0.40,     # entradas ease-out 250–400 ms
    "title_char_s": 0.022,                        # typewriter de títulos: 18–25 ms/carácter
    "command_char_s": 0.035,                      # typewriter de comandos: 35 ms/carácter
    "cursor_blink_s": 0.53,
    "card_enter": "slide-up+fade",                # tarjetas: slide-in + fade
    "strike_s": 0.35,                             # tachado animado en accent para listas "sin X"
    "counter_s": 0.9,                             # contador animado para cifras
}
SFX = {
    "level_db_vs_voice": -18,                     # efectos 18 dB por debajo de la voz
    "files": {"swoosh": SFX_DIR / "swoosh.wav", "tick": SFX_DIR / "tick.wav", "pop": SFX_DIR / "pop.wav"},
    "rules": {"typewriter_end": "tick", "card_enter": "swoosh", "number_end": "pop"},
}


# ------------------------------------------------------------------ texto quemado (libass): callouts y karaoke
# Sin caja en ningún estilo (BorderStyle=1, Outline=0): texto plano con una sombra suave de 1 px en
# textTitle al 25 %. En libass, con BorderStyle=1 el BackColour ES el color de la sombra.

CAPTION_SHADOW = {"color": "textTitle", "alpha": 0.25, "px": 1}
# Umbral de contraste del acento sobre una zona oscura: por debajo se usa el acento claro del tema oscuro.
CAPTION_MIN_ACCENT_CONTRAST = 3.0


def caption_colors() -> dict:
    """Color roles of burned-in text (long-form callouts and Shorts karaoke), hex."""
    L, D = light(), dark()
    return {
        "callout_text": L["textTitle"],            # #0B1220: texto sobre zona clara
        "callout_keyword": L["accent"],            # #2563EB: la palabra clave
        "callout_cost": L["accent3"],              # cifras de costo (palabra clave con $, €, USD...)
        "callout_on_dark": L["surface1Alt"],       # #F8FAFC: texto sobre zona oscura (p. ej. la terminal)
        "callout_keyword_on_dark": D["ink"]["blue"],   # #4F8DF9: acento si #2563EB queda < 3:1 en la zona
        "callout_cost_on_dark": D["accent3"],
        "karaoke_text": L["textTitle"],            # Shorts: palabras no activas
        "karaoke_active": L["accent"],             # Shorts: palabra que se está diciendo
        "shadow": L[CAPTION_SHADOW["color"]],
        "shadow_alpha": CAPTION_SHADOW["alpha"],
    }


def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(value) -> float:
    """WCAG relative luminance (0 black – 1 white) of a color (hex/rgba string or (r, g, b))."""
    r, g, b = (rgba(value)[:3] if isinstance(value, str) else value[:3])
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(l1: float, l2: float) -> float:
    """WCAG contrast ratio between two relative luminances."""
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# ------------------------------------------------------------------ explainroo (escenas EXPLAIN)
# Un proyecto de explainroo recibe: un look propio (look.json, docs settings "Custom looks"), las fuentes
# y efectos copiados en assets/, y `const THEME = {...}` antepuesto a scenes.js. scenes.js no lleva
# ningún color, fuente ni tiempo escrito a mano: todo sale de scenes_theme().

LOOK_NAME = "tbl-paper"                         # no puede ser el nombre de un look integrado ("paper" lo es)
LOOK_FILE = "look.json"                         # relativo a la carpeta del proyecto explainroo
SUBTITLE_BAND = 0.20                            # 20 % inferior del cuadro: libre (controles del reproductor);
                                                # los callouts se apoyan justo encima (y <= 864 px)
_ROLE_FAMILY = {"heading": "heading", "body": "body", "mono": "mono"}


def _css_shadow(value: str) -> dict:
    """'0 2px 8px rgba(15,23,42,0.06)' -> {color, blur, x, y} for canvas (shadowBlur ≈ CSS blur)."""
    m = re.match(r"\s*(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+([\d.]+)(?:px)?\s+(rgba?\([^)]*\)|#[0-9A-Fa-f]+)", value)
    if not m:
        raise ValueError(f"unrecognized shadow: {value}")
    return {"x": float(m.group(1)), "y": float(m.group(2)), "blur": float(m.group(3)), "color": m.group(4).replace(" ", "")}


def _rgba_str(value: str, alpha: float) -> str:
    r, g, b, _ = rgba(value)
    return f"rgba({r},{g},{b},{alpha:g})"


def font_assets() -> list[dict]:
    """FONT_FILES fonts that exist, except LIBASS_ONLY_FONTS: [{family, weight, path, src}] (src relative to
    the explainroo project)."""
    out = []
    for key, path in FONT_FILES.items():
        if key in LIBASS_ONLY_FONTS:
            continue
        role, weight = key.rsplit("_", 1)
        if Path(path).is_file():
            out.append({"family": FONT_FAMILIES[_ROLE_FAMILY[role]], "weight": int(weight),
                        "path": Path(path), "src": f"assets/fonts/{Path(path).name}"})
    return out


def sfx_assets() -> dict:
    """SFX["files"] effects that exist: name -> {path, src}."""
    return {name: {"path": Path(p), "src": f"assets/sfx/{Path(p).name}"}
            for name, p in SFX["files"].items() if Path(p).is_file()}


def explainroo_look() -> dict:
    """Custom explainroo look (schema from engine/themes.js + src/project.js loadLook)."""
    p, L, D = palette(), light(), dark()
    return {
        "extends": "clean",                      # tarjetas planas sin trazo a mano; lo demás se reemplaza aquí
        "name": LOOK_NAME,
        "dark": False,
        "bg": p["bg"], "ink": p["title"], "muted": p["muted"], "surface": p["card_bg"],
        "accent": "blue",                        # nombre de color de explainroo -> colors.blue = accent del tema
        "colors": {
            "blue": p["accent"], "teal": p["accent2"], "orange": p["cost"], "yellow": p["warning"],
            "green": p["positive"], "red": p["negative"], "purple": p["kpi"], "gray": p["muted"],
            "ink": p["title"],
        },
        "fonts": {
            "display": {"family": FONT_FAMILIES["heading"], "weight": SCALE["title_weight"]},
            "body": {"family": FONT_FAMILIES["body"], "weight": SCALE["body_weight"]},
            "hand": {"family": FONT_FAMILIES["body"], "weight": SCALE["body_weight"]},
            "mono": {"family": FONT_FAMILIES["mono"], "weight": SCALE["mono_weight"]},
        },
        "background": "plain",                   # la cuadrícula de 48 px la dibuja scenes.js con THEME.c.grid
        "radius": CARD["radius_px"],
        "stroke": {"rough": False, "width": 3},  # flechas y líneas; las tarjetas usan CARD.border_px
        "terminal": {"bg": p["term_bg"], "fg": p["term_text"], "prompt": p["term_prompt"],
                     "muted": p["term_muted"], "bar": p["term_bar"]},
        "code": {"bg": p["term_bg"], "fg": p["term_text"], "comment": p["term_muted"], "keyword": D["ink"]["blue"],
                 "string": p["term_ok"], "number": p["term_warn"], "fn": p["term_prompt"], "punct": p["term_muted"],
                 "lineNo": p["term_muted"], "highlight": _rgba_str(D["accent"], 0.25), "border": p["term_bg"]},
        "caption": {"bg": _rgba_str(L["textTitle"], 0.86), "fg": p["card_bg"], "active": p["accent"]},
    }


def explainroo_video() -> dict:
    """video.json keys set by the theme: look, custom fonts, brand and effects.

    sfx False: explainroo adds no sounds of its own (entrances, transitions); s.sound() effects
    (ours, assets/sfx) still play (docs scene-api "Sound")."""
    p = palette()
    return {
        "theme": LOOK_FILE,
        "fonts": [{"family": f["family"], "src": f["src"], "weight": f["weight"]} for f in font_assets()],
        "brand": {"accent": p["accent"], "background": p["bg"], "ink": p["title"],
                  "font": FONT_FAMILIES["body"], "headline": FONT_FAMILIES["heading"]},
        "sfx": False,
    }


def scenes_theme() -> dict:
    """scenes.js `const THEME`: color roles, fonts, scales, card, motion and effects."""
    p, L = palette(), light()
    bg = p["bg"]
    c = dict(p)
    c.update({
        "glow_alpha": GLOW["alpha"], "glow_radius": round(GLOW["radius_frac"] * 1920),
        "track": hex_of(over(L["line"], bg)),                        # pista vacía de barras/medidores
        "accent_tint": hex_of(over(p["accent"], p["card_bg"], 0.16)),  # rellenos suaves (no texto)
        "accent2_tint": hex_of(over(p["accent2"], p["card_bg"], 0.16)),
        "cost_tint": hex_of(over(p["cost"], p["card_bg"], 0.14)),
    })
    sfx = sfx_assets()
    return {
        "name": NAME, "version": VERSION,
        "c": c,
        "font": {"title": "display", "body": "body", "mono": "mono"},       # roles de fuente de explainroo
        "family": dict(FONT_FAMILIES),
        "size": {"title": SCALE["title_px"], "subtitle": SCALE["subtitle_px"], "body": SCALE["body_px"],
                 "mono": SCALE["mono_px"], "small": SCALE["small_px"],
                 "figure_scale": SCALE["figure_scale"]},
        "weight": {"title": SCALE["title_weight"], "body": SCALE["body_weight"], "mono": SCALE["mono_weight"]},
        "grid": {"px": GRID["px"], "width": 1},
        "card": {"radius": CARD["radius_px"], "border": CARD["border_px"], "shadow": _css_shadow(CARD["shadow"])},
        "motion": {
            "enter": round((MOTION["enter_min_s"] + MOTION["enter_max_s"]) / 2, 3),   # 0,325 s
            "enter_min": MOTION["enter_min_s"], "enter_max": MOTION["enter_max_s"],
            "title_cps": round(1 / MOTION["title_char_s"], 2),
            "command_cps": round(1 / MOTION["command_char_s"], 2),
            "cursor_blink": MOTION["cursor_blink_s"],
            "card_enter": "rise",               # explainroo: sube 44 px + fundido, ease-out (MOTION card_enter)
            "strike": MOTION["strike_s"], "counter": MOTION["counter_s"],
        },
        "sfx": {"files": {name: v["src"] for name, v in sfx.items()}, "volume": 1.0, "rules": dict(SFX["rules"])},
        "frame": {"subtitle_top": round(1080 * (1 - SUBTITLE_BAND))},       # y > 864 px: reservado
    }


def look_hash() -> str:
    """Fingerprint of the look, video.json, THEME and copied files (fonts, effects): cache key."""
    import hashlib
    files = [(str(f["path"].name), f["path"].stat().st_size, f["path"].stat().st_mtime_ns) for f in font_assets()]
    files += [(n, v["path"].stat().st_size, v["path"].stat().st_mtime_ns) for n, v in sorted(sfx_assets().items())]
    blob = json.dumps([VERSION, explainroo_look(), explainroo_video(), scenes_theme(), files], sort_keys=True,
                      default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def write_explainroo_assets(proj: Path) -> None:
    """Write look.json and copy fonts and effects into an explainroo project."""
    import shutil
    (Path(proj) / LOOK_FILE).write_text(json.dumps(explainroo_look(), indent=1), encoding="utf-8")
    for sub, items in (("fonts", [(f["path"], f["src"]) for f in font_assets()]),
                       ("sfx", [(v["path"], v["src"]) for v in sfx_assets().values()])):
        if items:
            (Path(proj) / "assets" / sub).mkdir(parents=True, exist_ok=True)
        for src, rel in items:
            shutil.copy2(src, Path(proj) / rel)


def summary() -> dict:
    """What gets recorded in each run's manifest."""
    t = tokens()
    return {"name": NAME, "version": VERSION, "tokens": f"dm-design-system {t['meta']['version']}",
            "palette": palette(), "scale": SCALE, "fonts": FONT_FAMILIES, "grid": GRID, "glow": GLOW, "card": CARD,
            "motion": MOTION, "sfx_db": SFX["level_db_vs_voice"], "captions": caption_colors()}

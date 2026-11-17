"""Assembly with FFmpeg: SCREEN placeholders (sub-pixel Ken Burns), music ducked under
the voice, burned-in callouts over SCREEN scenes (3–6 words with the keyword, no box), the full
transcript as final.srt (closed captions, uploaded by the Publisher), subtitle sync report and the final
1080p30 render."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

from . import theme_paper
from .config import PROJECT_ROOT

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FONTS_DIR = Path(r"C:\Windows\Fonts")
FONT_BOLD = next((FONTS_DIR / f for f in ("segoeuib.ttf", "arialbd.ttf") if (FONTS_DIR / f).exists()), None)
FONT_REG = next((FONTS_DIR / f for f in ("segoeui.ttf", "arial.ttf") if (FONTS_DIR / f).exists()), None)
# Política (2026-11-16): el long-form NO quema la transcripción. final.srt lleva la transcripción completa
# (closed captions, los sube el Publicador); en pantalla solo hay callouts sobre escenas SCREEN.
# Fuente, tamaños y colores salen de theme_paper; aquí solo la geometría.
SUB_FONT_KEY = "body_600"
SUB_FONT_FILE = theme_paper.FONT_FILES[SUB_FONT_KEY]       # assets/fonts/Inter-SemiBold.ttf
SUB_FONT_NAME = theme_paper.FONT_FACES[SUB_FONT_KEY]       # "Inter SemiBold" (libass, Bold=0)
SUB_LEAD_S = 0.12              # el subtítulo / callout aparece 120 ms antes que su audio
SUB_MIN_PHRASE_S = 1.0         # frases más cortas se unen con una vecina (si el resultado cabe)
SUB_GAP_FILL_S = 0.25          # huecos menores entre frases se rellenan (evita parpadeo)
SUB_LINE_CHARS = 42            # máx. caracteres por línea del SRT (con espacios y puntuación); máx. 2 líneas
SUB_TARGET_S = (1.2, 3.0)      # duración cómoda de lectura de un subtítulo (coste blando fuera)
# Tamaño ASS = alto de línea en px (libass: winAscent+winDescent = 72 px). Con Inter (win 2269+660 de
# 2048 unidades) el em queda en 50,3 px, mayúsculas 36,6 px, x-height 27,5 px (≈ Segoe UI a 72).
SUB_FONT_SIZE = theme_paper.SCALE["subtitle_px"]
SUB_MARGIN_H = 140             # márgenes izquierdo/derecho del texto quemado
# Ancho de línea con que se corta final.srt: el del antiguo subtítulo quemado (1920 − 2×140 − 2×10 de
# relleno de caja). Se conserva para que el SRT salga exactamente igual que antes del cambio de política.
SUB_MAX_W_PX = 1620
KB_ZOOM = 1.05                 # Ken Burns: zoom máximo por escena, lineal
SCREEN_DESIGN = 12  # subir al cambiar el diseño del placeholder o del Ken Burns (invalida su caché)
PANEL_FRAC = 0.80              # SCREEN panels: content only in the top 80 % of the frame
SUB_BAND_TOP = 216             # 20 % inferior (y > 864): sin contenido ni texto (controles del reproductor)
CALLOUT_RESERVE_PX = 100       # franja de 100 px (a 1080p) sobre el 20 % inferior: solo para el callout
SCREEN_PANEL_FRAC = PANEL_FRAC - CALLOUT_RESERVE_PX / 1080   # paneles SCREEN: hasta y = 764 a 1080p
LETTERBOX = "0x" + theme_paper.palette()["bg"].lstrip("#")   # relleno de grabaciones: bg-body del tema paper
# Callout (long-form): una línea centrada, Inter 600 a 72 (ASS), apoyada encima de la franja inferior. La caja
# de línea de libass (winAscent + winDescent, no la tinta) termina en y = 850, el mismo borde inferior que
# las tarjetas de los paneles SCREEN (screens._Stage.bottom = 864 − 14 px de sombra): la tinta, descendentes
# incluidos, queda DENTRO de una tarjeta que llega al fondo (si no, las colas de p/g/y caían sobre el fondo
# claro bajo una terminal oscura) y nada entra en el 20 % inferior. Línea base en y ≈ 834.
CALLOUT_FONT_KEY = "body_600"
CALLOUT_SIZE = theme_paper.SCALE["callout_px"]
CALLOUT_MARGIN_H = SUB_MARGIN_H
CALLOUT_MAX_W_PX = 1920 - 2 * CALLOUT_MARGIN_H     # 1640 px: si no cabe se quitan palabras (nunca 2 líneas
                                                   # ni un tamaño menor)
CALLOUT_CARD_GAP = 14                              # = margen de sombra bajo las tarjetas (screens._Stage.bottom)
CALLOUT_MARGIN_V = SUB_BAND_TOP + CALLOUT_CARD_GAP # Alignment 2: borde inferior de la caja de línea en y = 850
CALLOUT_WORDS = (3, 6)         # palabras por callout: la clave + 2–4 vecinas de su oración
CALLOUT_MIN_S = 0.5            # un callout que quedaría < 0,5 s en la escena SCREEN se omite
CALLOUT_SAMPLES = 5            # fotogramas muestreados bajo el callout para medir la luminancia de la zona
# Overlay (divulgación de afiliados): arriba a la derecha, sin caja.
OVERLAY_SIZE = 40

# Todos los clips salen con los mismos metadatos de color. Sin esto, el concat por copia mezcla
# clips yuvj420p/pc (explainroo) con yuv420p/tv (FFmpeg) y hay planos que cambian de brillo
# (20 -> 33 en luma: conversión de rango completo a limitado). Encontrado el 2026-11-16.
COLOR_VF = "scale=out_range=tv:out_color_matrix=bt709,format=yuv420p"
COLOR_ARGS = ["-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]


def ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", creationflags=_NOWIN)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}): {p.stderr.strip()[-600:]}")


def ffmpeg_version() -> str:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True, creationflags=_NOWIN)
    return p.stdout.splitlines()[0] if p.stdout else "?"


# ---------------------------------------------------------------- Ken Burns subpíxel

def kenburns(src_png: Path, out_mp4: Path, frames: int, fps: int, W: int, H: int,
             zoom_in: bool = True, zmax: float = KB_ZOOM) -> None:
    """Linear zoom 1 -> zmax (or the reverse) with per-frame fractional coordinates
    (perspective, cubic interpolation) at 1080p over the lanczos-downscaled source; the PNG is
    decoded only once (loop filter).
    Measured 2026-11-16 on a 5 s scene: max deviation 0.089 px, RMS 0.029 px, 0 backtracks,
    1.5 s render (plain zoompan: 1.136 px, 0.443 px, 432 backtracks; perspective at 2x: 0.075 px
    but 7.9 s)."""
    n1 = max(1, frames - 1)
    d = zmax - 1
    # `in` de perspective empieza en 1: (in-1) hace que el primer frame sea exactamente 1.00 y el último zmax
    z = f"(1+{d}*(in-1)/{n1})" if zoom_in else f"({zmax}-{d}*(in-1)/{n1})"
    x0, y0, x1, y1 = f"(W-W/{z})/2", f"(H-H/{z})/2", f"(W+W/{z})/2", f"(H+H/{z})/2"
    pers = (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}'"
            f":interpolation=cubic:sense=source:eval=frame")
    tmp = out_mp4.with_name(out_mp4.stem + ".writing.mp4")
    ffmpeg(["-i", str(src_png),
            "-vf", f"scale={W}:{H}:flags=lanczos,loop=loop=-1:size=1:start=0,setpts=N/{fps}/TB,{pers},{COLOR_VF}",
            "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
            *COLOR_ARGS, "-r", str(fps), str(tmp)])
    os.replace(tmp, out_mp4)


# ---------------------------------------------------------------- SCREEN placeholders

def _font(path: Path | None, size: int):
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default()


def screen_image(scene, path: Path, W: int, H: int) -> None:
    """Temporary placeholder, at 2x, in the paper theme (screens.placeholder_png): grid background and a
    white card with the scene description. Everything stays above the subtitle band EVEN at the
    Ken Burns maximum zoom (towards the center)."""
    from . import screens
    screens.placeholder_png(scene.label, path, W, H, KB_ZOOM, SCREEN_PANEL_FRAC)


def render_screen(scene, cfg: dict, cache_dir: Path) -> dict:
    fps = cfg["video"]["fps"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    zoom_in = scene.index % 2 == 0
    key = hashlib.sha1(json.dumps([scene.label, scene.frames, zoom_in, W, H, fps, KB_ZOOM, SCREEN_DESIGN])
                       .encode()).hexdigest()[:16]
    out = cache_dir / "screen" / f"{scene.id}_{key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cached = out.exists()
    if not cached:
        png = out.with_suffix(".png")
        screen_image(scene, png, W, H)
        kenburns(png, out, scene.frames, fps, W, H, zoom_in)
        png.unlink(missing_ok=True)
    scene.clip = out
    return {"scene": scene.index, "label": scene.label, "frames": scene.frames, "cached": cached,
            "ken_burns": f"{'in' if zoom_in else 'out'} 1.00↔{KB_ZOOM}", "seconds": round(time.perf_counter() - t0, 2)}


# ---------------------------------------------------------------- SCREEN con grabación real

def _probe_audio_s(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, creationflags=_NOWIN)
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe could not read the duration of {path}: {p.stderr.strip()[-300:] or p.stdout.strip()}")


def _secs(v) -> float:
    """'75', '75.5', '1:15', '00:01:15.5' -> seconds."""
    try:
        parts = [float(p) for p in str(v).strip().split(":")]
    except ValueError:
        parts = []
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        raise ValueError(f"invalid time {v!r}: use seconds (75.5), m:ss (1:15) or hh:mm:ss.s (00:01:15.5), "
                         f"with a decimal point")
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def _probe_video(path: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_NOWIN)
    try:
        j = json.loads(p.stdout)
        st = j["streams"][0]
        num, den = st["r_frame_rate"].split("/")
        return {"width": st["width"], "height": st["height"], "fps": round(float(num) / float(den), 3),
                "duration_s": round(float(j["format"]["duration"]), 3)}
    except (ValueError, KeyError, IndexError, ZeroDivisionError):
        raise RuntimeError(f"ffprobe could not read {path} as a video with a duration (damaged file, an OBS recording "
                           f"that was not closed, or not a video?): {p.stderr.strip()[-300:]}") from None


def _zoom_perspective(W: int, H: int, region: tuple, frames: int, ramp: float = 0.3, zmax: float = 2.5) -> str:
    """Smooth (smoothstep) zoom from the full frame to `region` (x, y, w, h as fractions of the
    output frame) over `ramp` of the scene, then hold. Per-frame fractional coordinates.
    Zooms around a fixed point F (homothety): every point moves away from F monotonically, without the
    wobble of interpolating center and zoom separately (the region drifted ~20 px outwards before settling)."""
    x, y, w, h = region
    zt = max(1.0, min(zmax, 1 / max(w, h, 1e-3)))           # la ventana 16:9 debe contener la región
    if zt < 1.0001:
        return "null"                                         # la región ya es el cuadro completo
    cx, cy = (x + w / 2) * W, (y + h / 2) * H
    ww, wh = W / zt, H / zt                                   # ventana final
    cx = min(max(cx, ww / 2), W - ww / 2)                     # dentro del cuadro
    cy = min(max(cy, wh / 2), H - wh / 2)
    fx = (cx - ww / 2) / (1 - 1 / zt)                         # punto fijo: ventana(z) = F + (cuadro - F)/z
    fy = (cy - wh / 2) / (1 - 1 / zt)
    K = max(1, int(frames * ramp))
    p = f"(min((in-1)/{K},1))"                                # `in` de perspective empieza en 1
    s = f"({p}*{p}*(3-2*{p}))"                                # smoothstep
    z = f"(1+{zt - 1:.6f}*{s})"
    x0, x1 = f"({fx:.4f}-{fx:.4f}/{z})", f"({fx:.4f}+{W - fx:.4f}/{z})"
    y0, y1 = f"({fy:.4f}-{fy:.4f}/{z})", f"({fy:.4f}+{H - fy:.4f}/{z})"
    return (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}'"
            f":interpolation=cubic:sense=source:eval=frame")


def render_recording(scene, cfg: dict, cache_dir: Path) -> dict:
    """SCREEN scene from a recording (OBS .mkv/.mp4): trims [in, out], speeds it up to fit the
    scene duration (max video.max_speed, 4x) and applies an optional zoom to a region."""
    fps = cfg["video"]["fps"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    max_speed = cfg["video"].get("max_speed", 4.0)
    prm = scene.params
    src = Path(prm["src"])
    src = src if src.is_absolute() else PROJECT_ROOT / src
    if not src.exists():
        raise FileNotFoundError(f"scene {scene.index}: recording not found: {src}")
    info = _probe_video(src)
    dur, warnings = info["duration_s"], []
    try:
        t_in, t_out_req = _secs(prm.get("in", 0)), _secs(prm.get("out", dur))
    except ValueError as e:
        raise ValueError(f"scene {scene.index}: {e}") from None
    if t_in >= dur:
        raise ValueError(f"scene {scene.index}: in ({t_in:g} s) is past the end of the recording "
                         f"({dur:g} s, {src.name})")
    if t_out_req <= t_in:
        raise ValueError(f"scene {scene.index}: out ({t_out_req:g} s) must be greater than in ({t_in:g} s)")
    t_out = min(t_out_req, dur)
    if t_out_req > dur + 0.05:
        warnings.append(f"out ({t_out_req:g} s) is past the end of the recording: using {dur:g} s")
    seg, target = t_out - t_in, scene.frames / fps
    speed = seg / target
    if speed > max_speed:
        warnings.append(f"the {seg:.1f} s segment does not fit in {target:.1f} s at {max_speed:g}x: only the first "
                        f"{target * max_speed:.1f} s are shown (up to {t_in + target * max_speed:.1f} s of the "
                        f"recording). Trim in/out or split the scene.")
        speed = max_speed
    elif speed < 1:
        warnings.append(f"the {seg:.1f} s segment is shorter than the scene ({target:.1f} s): it plays at 1x "
                        f"and the last frame is held for {target - seg:.1f} s. Widen in/out to avoid the freeze.")
        speed = 1.0
    region = None
    if prm.get("zoom"):
        try:
            region = tuple(float(v) for v in str(prm["zoom"]).split(","))
        except ValueError:
            region = ()
        if (len(region) != 4 or region[2] <= 0 or region[3] <= 0 or min(region[:2]) < 0
                or region[0] + region[2] > 1.001 or region[1] + region[3] > 1.001):
            raise ValueError(f"scene {scene.index}: invalid zoom={prm['zoom']!r}: expected x,y,w,h as fractions "
                             f"of the output frame (0–1, with x+w ≤ 1 and y+h ≤ 1), e.g. 0.55,0.08,0.4,0.4")
    st = src.stat()
    key = hashlib.sha1(json.dumps([str(src), st.st_size, st.st_mtime_ns, t_in, t_out, scene.frames, region,
                                   max_speed, W, H, fps, "rec-v4", LETTERBOX]).encode()).hexdigest()[:16]
    out = cache_dir / "recording" / f"{scene.id}_{key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cached = out.exists()
    if not cached:
        chain = [f"setpts=(PTS-STARTPTS)/{speed:.6f}", f"fps={fps}"]
        # la grabación vive en un panel del SCREEN_PANEL_FRAC superior; debajo quedan la franja del callout
        # (100 px) y el 20 % inferior libre.
        # El zoom (si hay) se aplica dentro del panel y sus coordenadas son fracciones del panel.
        PH = int(round(H * SCREEN_PANEL_FRAC / 2)) * 2
        chain += [f"scale={W}:{PH}:force_original_aspect_ratio=decrease:flags=lanczos",
                  f"pad={W}:{PH}:(ow-iw)/2:(oh-ih)/2:color={LETTERBOX}"]
        if region:
            chain.append(_zoom_perspective(W, PH, region, scene.frames))
        chain += [f"pad={W}:{H}:0:0:color={LETTERBOX}", "tpad=stop_mode=clone:stop_duration=600", COLOR_VF]
        tmp = out.with_name(out.stem + ".writing.mp4")
        ffmpeg(["-ss", f"{t_in:.3f}", "-t", f"{seg:.3f}", "-i", str(src), "-an", "-vf", ",".join(chain),
                "-frames:v", str(scene.frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                *COLOR_ARGS, "-r", str(fps), str(tmp)])
        os.replace(tmp, out)
    scene.clip = out
    return {"scene": scene.index, "label": scene.label, "source": str(src.relative_to(PROJECT_ROOT))
            if src.is_relative_to(PROJECT_ROOT) else str(src), "source_info": info, "in_s": t_in, "out_s": t_out,
            "segment_s": round(seg, 3), "scene_s": round(target, 3), "speed": round(speed, 3),
            "zoom": region, "warnings": warnings, "cached": cached, "seconds": round(time.perf_counter() - t0, 2)}


def render_screen_panel(scene, cfg: dict, cache_dir: Path) -> dict:
    """SCREEN scene with real content (show=file|terminal|image, see screens.py), animated in the paper theme
    (PIL frames -> FFmpeg) with its SFX track (swoosh / tick; silent if there are no events)."""
    from . import screens
    fps = cfg["video"]["fps"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    key = hashlib.sha1(json.dumps([screens.content_key(scene), scene.frames, W, H, fps, theme_paper.VERSION,
                                   screens.VERSION]).encode()).hexdigest()[:16]
    out = cache_dir / "screen" / f"{scene.id}_{key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    cached = out.exists()
    info = {}
    if not cached:
        info = screens.render_clip(scene, out, W, H, fps, scene.frames)
    scene.clip = out
    return {"scene": scene.index, "label": scene.label, "frames": scene.frames, "cached": cached,
            "show": scene.params.get("show"),
            "source": scene.params.get("capture") or scene.params.get("path"), "panel": info,
            "animation": f"{theme_paper.NAME} v{theme_paper.VERSION} · screens v{screens.VERSION}",
            "warnings": info.get("warnings", []), "seconds": round(time.perf_counter() - t0, 2)}


def render_screen_scene(scene, cfg: dict, cache_dir: Path) -> dict:
    """Real recording if the tag has src=..., real panel if it has show=..., otherwise a placeholder.
    A src= recording that doesn't exist yet (OBS pending) falls back to the show= panel (or the
    placeholder) with a warning, so the video can be reviewed before the recordings are made."""
    src = scene.params.get("src")
    if src and (PROJECT_ROOT / str(src)).exists():
        return render_recording(scene, cfg, cache_dir)
    if src:
        print(f"WARNING scene {scene.index}: recording {src} not found; using the "
              f"{'show= panel' if scene.params.get('show') else 'placeholder'} until it is recorded")
    if scene.params.get("show"):
        return render_screen_panel(scene, cfg, cache_dir)
    return render_screen(scene, cfg, cache_dir)


# ---------------------------------------------------------------- música

MUSIC_EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg")


def music_licenses(mdir: Path) -> dict[str, dict]:
    """Read assets/music/music.md: rows | file | title | artist | license | source | attribution |.
    A row without a title or a license does not count as documented. The header row is skipped
    whether it is in Spanish ("archivo", as music.md has it) or in English ("file")."""
    md = mdir / "music.md"
    rows: dict[str, dict] = {}
    if not md.exists():
        return rows
    empty = ("", "—", "-", "no")
    for line in md.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        s = s[1:-1] if s.endswith("|") else s[1:]  # solo los bordes: "| … | |" y "| … ||" dan 6 celdas
        cells = [c.strip() for c in s.split("|")]
        if (len(cells) >= 6 and cells[0] and cells[0].lower() not in ("archivo", "file")
                and not set(cells[0]) <= set(":-") and cells[1] not in empty and cells[3] not in empty):
            rows[cells[0]] = {"title": cells[1], "artist": cells[2], "license": cells[3], "source": cells[4],
                              "attribution": cells[5] if cells[5] not in empty else None}
    return rows


def make_music(cfg: dict, total_s: float, workdir: Path, wanted: str | None = None) -> tuple[Path, dict]:
    """Music bed as long as the video: the chosen track (script meta `music:`, config music.track or the
    first documented one in alphabetical order), normalized to −24 LUFS, looped with a 2 s crossfade
    if it is short, with fade in/out. A requested track that is missing or undocumented stops the run.
    No tracks: a generated tone, marked as placeholder."""
    mdir = PROJECT_ROOT / cfg["music"]["dir"]
    files = sorted(p for p in mdir.glob("*") if p.suffix.lower() in MUSIC_EXT) if mdir.exists() else []
    wanted = wanted or cfg["music"].get("track")
    if files:
        lics = music_licenses(mdir)
        documented = [f for f in files if f.name in lics]
        md = mdir / "music.md"
        if wanted:
            track = next((f for f in files if f.name == wanted), None)
            if track is None:
                raise RuntimeError(f"The requested track '{wanted}' does not exist in {mdir}. "
                                   f"Documented tracks: {[f.name for f in documented] or 'none'}")
            if track.name not in lics:
                raise RuntimeError(f"{track.name} is not documented in {md} (title and license)")
        elif documented:
            track = documented[0]
        else:
            raise RuntimeError(f"No track in {mdir} is documented in {md} (title and license): "
                               f"{[f.name for f in files]}")
        lic = lics[track.name]
        dur = _probe_audio_s(track)
        xf = 2.0
        n = 1 if dur >= total_s + 1 else int(np.ceil((total_s + 1 - xf) / max(1.0, dur - xf)))
        out = workdir / "music_bed.wav"
        args = []
        for _ in range(n):
            args += ["-i", str(track)]
        chain, last = [], "[0:a]"
        for k in range(1, n):
            # qsin = potencia constante: con tri el centro del cruce bajaba ~3 dB (medido 2026-11-16)
            chain.append(f"{last}[{k}:a]acrossfade=d={xf}:c1=qsin:c2=qsin[x{k}]")
            last = f"[x{k}]"
        fade_out = max(0.0, total_s - 3)
        chain.append(f"{last}aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-24:TP=-2:LRA=11,"
                     f"atrim=0:{total_s + 0.5:.2f},afade=t=in:d=1.5,afade=t=out:st={fade_out:.2f}:d=3[m]")
        ffmpeg([*args, "-filter_complex", ";".join(chain), "-map", "[m]", "-ar", "48000", str(out)])
        src = str(track.relative_to(PROJECT_ROOT)) if track.is_relative_to(PROJECT_ROOT) else str(track)
        # «source» = archivo usado (como en el placeholder); la columna «fuente» de music.md va en source_url
        return out, {**lic, "source": src, "source_url": lic["source"], "placeholder": False,
                     "track_s": round(dur, 1), "loops": n, "normalized_lufs": -24,
                     "available": [f.name for f in files]}
    out = workdir / "music_placeholder.wav"
    T = f"{total_s + 1:.2f}"
    notes = [(110.0, 0.5), (164.81, 0.35), (220.0, 0.25), (329.63, 0.12)]  # A2 E3 A3 E4
    args: list[str] = []
    for f, _ in notes:
        args += ["-f", "lavfi", "-i", f"sine=f={f}:d={T}:sample_rate=48000"]
    chains = ";".join(f"[{i}]volume={v}[n{i}]" for i, (_, v) in enumerate(notes))
    mix = "".join(f"[n{i}]" for i in range(len(notes)))
    fade_out = max(0.0, total_s - 3)
    graph = (f"{chains};{mix}amix=inputs={len(notes)}:normalize=0,tremolo=f=0.15:d=0.35,"
             f"lowpass=f=900,afade=t=in:d=2,afade=t=out:st={fade_out:.2f}:d=3,volume=0.6,"
             f"aformat=channel_layouts=stereo[m]")
    ffmpeg([*args, "-filter_complex", graph, "-map", "[m]", "-ar", "48000", str(out)])
    return out, {"source": "generated", "placeholder": True,
                 "recipe": "FFmpeg sines A2+E3+A3+E4, tremolo 0.15 Hz, lowpass 900 Hz",
                 "note": "PLACEHOLDER: replace with royalty-free music in assets/music/"}


# ---------------------------------------------------------------- subtítulos

# Palabras que nunca cierran una línea ni un subtítulo, salvo que lleven puntuación pegada
# («...what it is.» sí puede cerrar): artículos y determinantes, posesivos, auxiliares y modales
# (también contraídos), preposiciones, conjunciones y los verbos que piden complemento.
_SUB_NO_END = frozenset("""
a an the this that these those its their our your his her my every each no some any another
either neither such whose
is are was were be been being am will would shall can could should may might must do does did
has have had it's that's there's here's what's we're they're you're i'm we've they've i've
we'll they'll it'll isn't aren't wasn't weren't don't doesn't didn't won't wouldn't can't
couldn't shouldn't hasn't haven't hadn't
to of in on at for from with by into onto over under about as than per via like through
between across after before during without within until since toward towards among upon
and or but so nor if when while because
go goes see sees move moves become becomes get gets
""".split())
# Finales tolerables pero feos (coste blando): sujeto suelto, negación, intensificadores.
_SUB_WEAK_END = frozenset("""i we you they he she not very more less most just only also there
how what which who where why""".split())
# Buen sitio para cortar: JUSTO ANTES de una conjunción, preposición o relativo.
_SUB_GOOD_BEFORE = frozenset("""and or but so nor if when while because than as to of in on at
for from with by into onto over under about per via like through between across after before
during without within until since where which who that""".split())
_SUB_HARD = 1000.0             # coste de romper una regla dura (solo si no hay alternativa)
_SUB_FONT: dict = {}


def _sub_word(u) -> str:
    """Normalized word (lowercase, no punctuation) to look up in the lists."""
    s = u.display.lower().replace("’", "'")
    return "".join(c for c in s if c.isalnum() or c == "'").strip("'")


def _sub_punct(u) -> str:
    """The unit's final punctuation ('' if none); ignores closing quotes and brackets."""
    s = u.display.rstrip(")]}\"'”’»")
    return s[-1] if s and s[-1] in ".,:;?!…—–" else ""


def _sub_end_ok(u) -> bool:
    return bool(_sub_punct(u)) or _sub_word(u) not in _SUB_NO_END


def _sub_text(units) -> str:
    return " ".join(u.display for u in units)


def _win_em(path: Path) -> float:
    """unitsPerEm / (usWinAscent + usWinDescent) of the TTF: em in px per px of ASS size (libass scales
    the font so that winAscent+winDescent = size). Read from the file with no dependencies."""
    import struct
    b = Path(path).read_bytes()
    tables = {b[12 + 16 * i: 16 + 16 * i]: struct.unpack(">I", b[20 + 16 * i: 24 + 16 * i])[0]
              for i in range(struct.unpack(">H", b[4:6])[0])}
    upm = struct.unpack(">H", b[tables[b"head"] + 18: tables[b"head"] + 20])[0]
    win_a, win_d = struct.unpack(">HH", b[tables[b"OS/2"] + 74: tables[b"OS/2"] + 78])
    return upm / (win_a + win_d)


def ass_text_px(text: str, font_file: Path, size: float) -> float:
    """Advance in px of the text as libass draws it with `font_file` at ASS size `size`.
    libass scales the font so that winAscent+winDescent = size and applies no hinting, so it is
    measured once at em=1000 with PIL and scaled linearly. PIL without raqm skips Inter's GPOS kerning:
    it overestimates slightly (conservative). Checked against libass 0.17.5 on 2026-11-16 on 7 lines of
    37–46 characters: PIL advance − libass ink = +3 to +7 px."""
    k = str(font_file)
    if k not in _SUB_FONT:
        _SUB_FONT[k] = (ImageFont.truetype(k, 1000), _win_em(Path(font_file)))
    f, em = _SUB_FONT[k]
    return f.getlength(text) * em * size / 1000


def _sub_px(text: str, size: float = SUB_FONT_SIZE) -> float:
    """Advance in px of an SRT line measured with SUB_FONT_FILE (keeps the SRT line breaking unchanged)."""
    return ass_text_px(text, SUB_FONT_FILE, size)


def _sub_line_pen(units) -> float:
    t = _sub_text(units)
    if len(t) > SUB_LINE_CHARS:
        return _SUB_HARD + 50 * (len(t) - SUB_LINE_CHARS)
    return 30.0 if _sub_px(t) > SUB_MAX_W_PX else 0.0    # cabe en caracteres pero no en px: \fs


def _sub_break_cost(units, k: int) -> float:
    """Cost of breaking between units[k-1] and units[k]. Best after punctuation, then before a
    conjunction/preposition; never after a _SUB_NO_END word. k == len(units): free."""
    if k >= len(units):
        return 0.0
    a, b = units[k - 1], units[k]
    p = _sub_punct(a)
    if not p and _sub_word(a) in _SUB_NO_END:
        return _SUB_HARD
    if p and p in ".?!…":
        c = 0.0
    elif p:
        c = 1.0
    elif _sub_word(b) in _SUB_GOOD_BEFORE:
        c = 3.0
    else:
        c = 6.0
    if not p and _sub_word(a) in _SUB_WEAK_END:
        c += 3.0
    if not p and a.keyword and b.keyword:          # no partir una palabra clave de varias palabras
        c += 4.0
    return c


def _sub_layout(units) -> tuple[float, list[list]]:
    """Best split of a subtitle into 1 or 2 lines: one line if it fits; otherwise the cheapest allowed
    break (punctuation > before a conjunction/preposition), balanced lines, no 1-word lines."""
    best = (_sub_line_pen(units), [list(units)])
    for k in range(1, len(units)):
        top, bot = units[:k], units[k:]
        bc = _sub_break_cost(units, k)
        c = 0.5 + _sub_line_pen(top) + _sub_line_pen(bot) + (bc if bc >= _SUB_HARD else 0.6 * bc)
        l1, l2 = len(_sub_text(top)), len(_sub_text(bot))
        r = (l1 - l2) / max(l1, l2, 1)
        c += 4 * r * r + (0.5 * r if r > 0 else 0)      # parejas; si no, mejor la de abajo más larga
        c += 4.0 * (len(top) == 1) + 4.0 * (len(bot) == 1)
        if c < best[0]:
            best = (c, [list(top), list(bot)])
    return best


def _sub_violations(lines: list[list], last_ok: bool = True) -> list[str]:
    """Hard rules broken by an already split subtitle (empty = OK)."""
    v = []
    for ln in lines:
        t = _sub_text(ln)
        if len(t) > SUB_LINE_CHARS:
            v.append(f"line of {len(t)} characters")
        elif _sub_px(t) > SUB_MAX_W_PX:
            v.append(f"line of {_sub_px(t):.0f} px")
    ends = [ln[-1] for ln in lines[:-1]] + ([] if last_ok else [lines[-1][-1]])
    v += [f"line ends with '{u.display}'" for u in ends if not _sub_end_ok(u)]
    return v


def _sub_dur(units) -> float | None:
    t0, t1 = units[0].start, units[-1].end
    return None if t0 is None or t1 is None else t1 - t0


def _phrases(scene) -> list[list]:
    """Optimal segmentation of the scene into subtitles (dynamic programming over the breaks).
    Hard (only broken when there is no other way, e.g. a unit longer than 42 characters): <= 2
    lines of <= SUB_LINE_CHARS that fit in px; no line or subtitle ends in a _SUB_NO_END word;
    a {shown|spoken} unit is never split. Soft: break after punctuation, then before a
    conjunction/preposition; duration SUB_TARGET_S; no 1-word subtitles."""
    U = scene.units
    n = len(U)
    if n == 0:
        return []
    lo, hi = SUB_TARGET_S
    best = [0.0] + [float("inf")] * n
    back = [0] * (n + 1)
    for j in range(1, n + 1):
        end_cost = _sub_break_cost(U, j)
        for i in range(j - 1, -1, -1):
            if j - i > 1 and len(_sub_text(U[i:j])) > 2 * SUB_LINE_CHARS + 1:
                break
            ev = U[i:j]
            c = 1.0 + _sub_layout(ev)[0] + end_cost        # 1.0 por subtítulo: sesgo leve
            d = _sub_dur(ev)
            if d is not None:
                c += 8.0 * max(0.0, lo - d) + 3.0 * max(0.0, d - hi)
            if j - i == 1:
                c += 5.0
            if best[i] + c < best[j]:
                best[j], back[j] = best[i] + c, i
    out, j = [], n
    while j > 0:
        out.append(list(U[back[j]:j]))
        j = back[j]
    return out[::-1]


def plan_phrases(scenes: list) -> list[dict]:
    """Phrases with their audio span (Whisper) and their on-screen span:
    - a phrase appears SUB_LEAD_S before its first word and lasts until the end of its last word;
    - a phrase shorter than SUB_MIN_PHRASE_S is merged with a neighbor (one from its scene) only if
      the merge still meets <= 2 lines, <= SUB_LINE_CHARS and the line-ending rule; otherwise it stays;
    - a gap shorter than SUB_GAP_FILL_S before the next one is filled (no flicker).
    Added keys: lines (1 or 2 lists of units), fs (reduced size or None), flags."""
    P = []
    scene_ends = {id(sc.units[-1]) for sc in scenes if sc.units}
    for sc in scenes:
        for ph in _phrases(sc):
            P.append({"units": list(ph), "scenes": [sc.index], "a0": sc.audio_offset + ph[0].start,
                      "a1": sc.audio_offset + ph[-1].end})
    merges = kept_short = 0
    i = 0
    while len(P) > 1 and i < len(P):
        p = P[i]
        if p["a1"] - p["a0"] >= SUB_MIN_PHRASE_S:
            i += 1
            continue
        # vecina preferida: de la misma escena y con la que la frase unida quede más corta
        cands = [j for j in (i - 1, i + 1) if 0 <= j < len(P)]
        same = [j for j in cands if set(P[j]["scenes"]) & set(p["scenes"])]
        pool = same or ([i + 1] if i + 1 < len(P) else [i - 1])
        pool = [j for j in pool if not _sub_violations(
            _sub_layout(P[min(i, j)]["units"] + P[max(i, j)]["units"])[1])]
        if not pool:                       # no cabe con ninguna vecina: se queda corta
            kept_short += 1
            i += 1
            continue
        j = min(pool, key=lambda q: len(P[q]["units"]))
        a, b = (p, P[j]) if j > i else (P[j], p)
        merged = {"units": a["units"] + b["units"], "scenes": sorted(set(a["scenes"] + b["scenes"])),
                  "a0": a["a0"], "a1": b["a1"]}
        lo = min(i, j)
        P[lo:lo + 2] = [merged]
        merges += 1
        i = lo
    clipped = 0
    for k, p in enumerate(P):
        p["s0"] = max(0.0, p["a0"] - SUB_LEAD_S)
        if k == 0 and p["s0"] < 0.25:      # la primera frase ya está en el primer frame
            p["s0"] = 0.0
        p["s1"] = p["a1"]
        if k + 1 < len(P):
            nxt0 = max(0.0, P[k + 1]["a0"] - SUB_LEAD_S)
            if nxt0 - p["s1"] < SUB_GAP_FILL_S:
                if nxt0 < p["s1"]:
                    clipped += 1
                p["s1"] = nxt0
        if p["s1"] - p["s0"] < 0.2:
            p["s1"] = p["s0"] + 0.2
    for p in P:
        p["lines"] = _sub_layout(p["units"])[1]
        w = max(_sub_px(_sub_text(ln)) for ln in p["lines"])
        # red de seguridad: si una línea no cabe en px, se reduce ESE subtítulo (nunca 3 líneas)
        p["fs"] = int(SUB_FONT_SIZE * SUB_MAX_W_PX / w) if w > SUB_MAX_W_PX else None
        p["flags"] = _sub_violations(p["lines"], last_ok=id(p["units"][-1]) in scene_ends)
        p["merges_total"] = merges
        p["clipped_total"] = clipped
        p["kept_short_total"] = kept_short
    return P


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _clean(s: str) -> str:
    return s.replace("{", "(").replace("}", ")").replace("\\", "/")


_SUB_MONEY = re.compile(r"[$€£¢]|\b(?:USD|EUR|cents?)\b", re.I)


# ---------------------------------------------------------------- estilos ASS sin caja (callouts, karaoke)

def caption_ass_colors() -> dict:
    """ASS colors of burned-in text (theme_paper.caption_colors) + the shadow color.
    No style has a box: BorderStyle=1 with Outline=0. In libass, with BorderStyle=1 the BackColour IS the
    shadow color, so "transparent background + soft shadow" = BackColour = textTitle at 25 % opacity
    (&HBF + BGR) and Shadow=1 px. OutlineColour is irrelevant with Outline=0 (also set to the shadow).
    No blur tag: with Outline=0 libass blurs the glyph FILL, not just the shadow (tested 2026-11-16)."""
    K = theme_paper.caption_colors()
    out = {k: theme_paper.ass_color(v) for k, v in K.items() if isinstance(v, str) and k != "shadow"}
    out["shadow"] = theme_paper.ass_color(K["shadow"], K["shadow_alpha"])
    out["hex"] = {k: v for k, v in K.items()}
    return out


def ass_style(name: str, font_key: str, size: int, primary: str, secondary: str, alignment: int,
              margin_h: int, margin_v: int) -> str:
    """One `Style:` line with no box: BorderStyle 1, Outline 0, Shadow theme_paper.CAPTION_SHADOW px.
    Bold=1 only for the RIBBI bold files (theme_paper.FONT_ASS_BOLD, e.g. "Inter" + Bold = Inter-Bold.ttf)."""
    face = theme_paper.FONT_FACES[font_key]
    bold = 1 if font_key in theme_paper.FONT_ASS_BOLD else 0
    sh = caption_ass_colors()["shadow"]
    shadow_px = theme_paper.CAPTION_SHADOW["px"]
    return (f"Style: {name},{face},{size},{primary},{secondary},{sh},{sh},{bold},0,0,0,100,100,0,0,"
            f"1,0,{shadow_px},{alignment},{margin_h},{margin_h},{margin_v},1")


def ass_header(W: int, H: int, styles: list[str]) -> str:
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(styles)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def burn_filter(ass_name: str = "subs.ass", fonts_dir: str = "fonts") -> str:
    """libass filter that burns an ASS file (relative to the ffmpeg cwd) with the theme's fonts. The same
    string is used by assemble() and by the preview frames."""
    return f"subtitles={ass_name}:fontsdir={fonts_dir}"


def copy_caption_fonts(fonts_dir: Path, keys=(SUB_FONT_KEY,)) -> None:
    fonts_dir.mkdir(parents=True, exist_ok=True)
    for k in keys:
        f = theme_paper.FONT_FILES[k]
        shutil.copy2(f, fonts_dir / Path(f).name)


# ---------------------------------------------------------------- callouts (long-form)
# Solo durante escenas SCREEN (también el gancho automático si es SCREEN); nunca sobre EXPLAIN. Uno por frase
# del subtítulo que cae en una SCREEN y tiene *palabra clave* (o un [CALLOUT: ...] en el guion).

_CALLOUT_NO_START = frozenset("a an the and or but so nor of to".split())   # nunca empiezan un callout
_CALLOUT_FUNC = _SUB_NO_END | _SUB_WEAK_END | _SUB_GOOD_BEFORE
_CALLOUT_WEAK_END = _SUB_WEAK_END | frozenset("out up off down".split())     # "2.3 GB out" -> mejor "out of eight"
_CALLOUT_STRIP_END = ".,;:—–…"


def _ends_sentence(u) -> bool:
    p = _sub_punct(u)
    return bool(p) and p in ".?!…"


def _callout_display(units) -> list[str]:
    """Display form of each unit (brace display values included), without the window's outer punctuation
    (a final ? or ! stays)."""
    words = [u.display for u in units]
    if words:
        words[0] = words[0].lstrip("([{\"'“‘«")
        w = words[-1]
        if not w.endswith(("?", "!")):
            w = w.rstrip(")]}\"'”’»").rstrip(_CALLOUT_STRIP_END)
        words[-1] = w
    return words


def _callout_fits(units) -> bool:
    return ass_text_px(" ".join(_callout_display(units)), theme_paper.FONT_FILES[CALLOUT_FONT_KEY],
                       CALLOUT_SIZE) <= CALLOUT_MAX_W_PX


def _keyword_groups(units) -> list[tuple[int, int]]:
    """Runs [i, j) of consecutive keyword units (a *multi word* keyword is one group)."""
    out, i = [], 0
    while i < len(units):
        if units[i].keyword:
            j = i
            while j < len(units) and units[j].keyword:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def select_callout(units, group: tuple[int, int]) -> tuple[list, list[str]]:
    """Callout words for the keyword run `group` of a phrase: the keyword plus 2–4 neighbouring units of
    the same sentence (3–6 words), single line at CALLOUT_SIZE. Cost (lower is better): starting on
    a/an/the/and/or/but/so/nor/of/to or ending on a word that cannot end a line (+10 each), fewer than 2
    neighbours when the sentence has more (+4 each), more than 6 words (+5 each), starting with the tail of
    another clause ("time, …", +10), ending mid-clause on a weak word ("out", "only", +2), crossing a comma/colon
    (+3 each), function words (+1), content
    words (−1), imbalance (+0.2 per unit). Windows that do not fit CALLOUT_MAX_W_PX are excluded.
    Returns (units, flags)."""
    g0, g1 = group
    a = g0
    while a > 0 and not _ends_sentence(units[a - 1]):
        a -= 1
    b = g1
    while b < len(units) and not _ends_sentence(units[b - 1]):
        b += 1
    avail = (g0 - a) + (b - g1)
    lo_n, hi_n = CALLOUT_WORDS[0] - 1, CALLOUT_WORDS[1] - 2      # 2–4 vecinas
    best, flags = None, []
    for i in range(a, g0 + 1):
        for j in range(g1, b + 1):
            n = (g0 - i) + (j - g1)
            if n > hi_n:
                continue
            win = units[i:j]
            if not _callout_fits(win):
                continue
            first, last = win[0], win[-1]
            c = 0.0
            if not first.keyword and _sub_word(first) in _CALLOUT_NO_START:
                c += 10
            if not last.keyword and _sub_word(last) in _SUB_NO_END:
                c += 10
            if not first.keyword and _sub_punct(first) in (",", ";"):   # "time, one keyword": cola de otra cláusula
                c += 10
            if not last.keyword and not _sub_punct(last) and _sub_word(last) in _CALLOUT_WEAK_END:
                c += 2
            c += 3 * sum(1 for u in win[:-1] if _sub_punct(u) and not u.keyword)   # cruza una coma o dos puntos
            c += 4 * max(0, min(lo_n, avail) - n)
            words = sum(len(u.display.split()) for u in win)
            c += 5 * max(0, words - CALLOUT_WORDS[1])
            for u in win:
                if u.keyword:
                    continue
                c += 1 if _sub_word(u) in _CALLOUT_FUNC else -1
            c += 0.2 * abs((g0 - i) - (j - g1))
            if best is None or c < best[0]:
                best = (c, win)
    if best is None:                       # ni la clave sola cabe: se recorta la clave (marcado)
        win = list(units[g0:g1])
        while len(win) > 1 and not _callout_fits(win):
            win.pop()
        flags.append("keyword alone does not fit the safe width")
        return win, flags
    if best[0] >= 10:
        flags.append("no window avoids a weak start/end word")
    return best[1], flags


def _trim_to_fit(units) -> tuple[list, list[str]]:
    """Explicit [CALLOUT]: drop units from the end farthest from the keyword until it fits one line."""
    win, flags = list(units), []
    kw = [k for k, u in enumerate(win) if u.keyword] or [0]
    while len(win) > 1 and not _callout_fits(win):
        left, right = kw[0], len(win) - 1 - kw[-1]
        if right >= left:
            win.pop()
        else:
            win.pop(0)
            kw = [k - 1 for k in kw]
        flags.append("trimmed to fit one line")
    return win, sorted(set(flags))


def _shots(scenes: list, fps: int) -> list[tuple[float, float, object]]:
    return [(s.start_frame / fps, (s.start_frame + s.frames) / fps, s) for s in scenes if s.frames > 0]


def plan_callouts(P: list[dict], scenes: list, fps: int) -> list[dict]:
    """One callout per phrase of `P` (plan_phrases) shown over a SCREEN shot that has a *keyword* in
    that shot (or a [CALLOUT: ...] from the script). Time: the phrase span (120 ms lead, gap fill)
    clipped to the SCREEN shot; skipped if under CALLOUT_MIN_S."""
    owner = {id(u): sc for sc in scenes for u in sc.units}
    explicit = {}
    for sc in scenes:
        for co in getattr(sc, "callouts", []):
            if co["unit"] < len(sc.units):
                explicit[id(sc.units[co["unit"]])] = co
    shots = _shots(scenes, fps)
    out = []
    for n, p in enumerate(P, 1):
        best = None
        for t0, t1, s in shots:
            ov = min(p["s1"], t1) - max(p["s0"], t0)
            if ov > 0 and (best is None or ov > best[0]):
                best = (ov, t0, t1, s)
        if best is None:
            continue
        _, t0, t1, shot = best
        co = next((explicit[id(u)] for u in p["units"] if id(u) in explicit), None)
        rec = {"phrase": n, "scene": shot.index, "kind": shot.kind,
               "s0": round(max(p["s0"], t0), 3), "s1": round(min(p["s1"], t1), 3),
               "shot_t0": round(t0, 3), "flags": []}
        if co is not None:
            units, flags = _trim_to_fit(co["units"])
            rec.update(source="CALLOUT", units=units, flags=flags)
            if not any(u.keyword for u in units):
                rec["flags"].append("[CALLOUT] without *keyword*")
            words = sum(len(u.display.split()) for u in units)
            if not CALLOUT_WORDS[0] <= words <= CALLOUT_WORDS[1]:
                rec["flags"].append(f"[CALLOUT] has {words} words (3–6 expected)")
        else:
            def in_shot(i, j, t0=t0, t1=t1):
                u0, u1 = p["units"][i], p["units"][j - 1]
                sc0, sc1 = owner[id(u0)], owner[id(u1)]
                if u0.start is None or u1.end is None:
                    return False
                mid = (sc0.audio_offset + u0.start + sc1.audio_offset + u1.end) / 2
                return t0 <= mid < t1
            groups = [g for g in _keyword_groups(p["units"]) if in_shot(*g)]
            if not groups:
                continue
            units, flags = select_callout(p["units"], groups[0])
            rec.update(source="auto", units=units, flags=flags)
        if shot.kind != "SCREEN":
            if co is not None:
                print(f"WARNING [CALLOUT: {co['text']}] falls on {shot.kind} scene {shot.index}: not burned "
                      f"(no burned text over EXPLAIN)")
            continue
        if rec["s1"] - rec["s0"] < CALLOUT_MIN_S:
            rec["flags"].append(f"skipped: only {rec['s1'] - rec['s0']:.2f} s inside the SCREEN shot")
            rec["skipped"] = True
        rec["words"] = _callout_display(rec["units"])
        rec["text"] = " ".join(rec["words"])
        rec["clip"] = str(shot.clip) if shot.clip else None
        out.append(rec)
    return out


def _callout_baseline(H: int) -> tuple[float, float]:
    """(em in px, baseline y) of the callout line: line-box bottom H − CALLOUT_MARGIN_V minus Inter's winDescent."""
    em = _win_em(Path(theme_paper.FONT_FILES[CALLOUT_FONT_KEY])) * CALLOUT_SIZE
    return em, H - CALLOUT_MARGIN_V - 660 / 2048 * em


def callout_box(text: str, W: int, H: int) -> tuple[int, int, int, int]:
    """Box (x0, y0, x1, y1) in px of the callout's ink: centered horizontally; vertically from the cap height
    to the descenders. Measured on the 2026-11-16 previews with libass 0.17.5: caps from y = 798 to 833 at
    1080p (MarginV 230), descenders to ≈ 846."""
    w = ass_text_px(text, theme_paper.FONT_FILES[CALLOUT_FONT_KEY], CALLOUT_SIZE)
    em, base = _callout_baseline(H)
    x0, x1 = int(max(0, W / 2 - w / 2 - 8)), int(min(W, W / 2 + w / 2 + 8))
    return x0, int(base - 0.73 * em - 2), x1, int(min(H, base + 0.24 * em + 2))


def _text_crossover() -> float:
    """Luminance where #0B1220 and #F8FAFC give the same WCAG contrast (≈ 0.19): darker zones get light text."""
    K = theme_paper.caption_colors()
    RL = theme_paper.relative_luminance
    return ((RL(K["callout_text"]) + 0.05) * (RL(K["callout_on_dark"]) + 0.05)) ** 0.5 - 0.05


def zone_luminance(clip: Path, t0: float, t1: float, box: tuple[int, int, int, int], base_y: float,
                   samples: int = CALLOUT_SAMPLES) -> list[dict]:
    """The zone under a callout in `samples` frames of `clip` between t0 and t1 (clip time), one dict per
    frame: lum = WCAG relative luminance of the MEDIAN pixel between the cap height and the baseline (what
    most of the text sits on; a mean would be misled by a light strip under a dark card, since light pixels
    dominate linear luminance); dark_frac = share of the whole ink box (descenders included) darker than the
    text crossover, to detect a card edge running under the text."""
    x0, y0, x1, y1 = box
    w, h = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    dur = max(t1 - t0, 0.05)
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t0):.3f}", "-t", f"{dur:.3f}", "-i", str(clip),
                        "-vf", f"fps={samples / dur:.5f},scale=in_color_matrix=bt709:in_range=tv:out_range=pc,"
                               f"crop={w}:{h}:{x0}:{y0},format=rgb24",
                        "-f", "rawvideo", "-"], capture_output=True, creationflags=_NOWIN)
    if p.returncode != 0 or not p.stdout:
        raise RuntimeError(f"could not sample {clip}: {p.stderr.decode('utf-8', 'replace')[-300:]}")
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, h, w, 3)
    c = fr.astype(np.float32) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    y = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    core = y[:, : max(1, int(round(base_y - y0)))]
    xo = _text_crossover()
    return [{"lum": round(float(np.median(core[i])), 4), "dark_frac": round(float((y[i] < xo).mean()), 3)}
            for i in range(len(y))]


def callout_colors(lum: float) -> dict:
    """Colors of one callout for a zone of (median) relative luminance `lum`: the text color with the higher
    WCAG contrast (#0B1220 or #F8FAFC: crossover at L ≈ 0.19); the keyword (or cost figure) keeps its
    color unless its contrast there is < theme_paper.CAPTION_MIN_ACCENT_CONTRAST (3:1); then it uses the
    lighter accent of the dark theme (on a dark zone) or the keyword accent (cost on a light zone)."""
    K = theme_paper.caption_colors()
    RL, CR = theme_paper.relative_luminance, theme_paper.contrast
    dark = CR(RL(K["callout_on_dark"]), lum) > CR(RL(K["callout_text"]), lum)
    text = K["callout_on_dark"] if dark else K["callout_text"]
    mn = theme_paper.CAPTION_MIN_ACCENT_CONTRAST
    kw = K["callout_keyword"]
    if CR(RL(kw), lum) < mn:
        kw = K["callout_keyword_on_dark"] if dark else kw
    cost = K["callout_cost"]
    if CR(RL(cost), lum) < mn:
        cost = K["callout_cost_on_dark"] if dark else kw
    return {"zone": "dark" if dark else "light", "text": text, "keyword": kw, "cost": cost,
            "contrast_text": round(CR(RL(text), lum), 2), "contrast_keyword": round(CR(RL(kw), lum), 2),
            "contrast_cost": round(CR(RL(cost), lum), 2)}


def callout_event(c: dict) -> str:
    A = theme_paper.ass_color
    t = A(c["colors"]["text"])
    parts = []
    disp = c["words"]
    for u, w in zip(c["units"], disp):
        if u.keyword:
            k = A(c["colors"]["cost"] if _SUB_MONEY.search(u.display) else c["colors"]["keyword"])
            parts.append(f"{{\\c{k}&}}{_clean(w)}{{\\c{t}&}}")
        else:
            parts.append(_clean(w))
    # \q2: sin cortes automáticos (siempre una línea; ya se comprobó que cabe)
    return (f"Dialogue: 0,{_ts_ass(c['s0'])},{_ts_ass(c['s1'])},Callout,,0,0,0,,"
            f"{{\\q2\\c{t}&}}" + " ".join(parts))


def build_subtitles(scenes: list, cfg: dict, ass_path: Path, srt_path: Path) -> tuple[dict, list[dict]]:
    """final.srt = the FULL transcript (same segmentation, line breaking and timing as before; uploaded as
    closed captions by the Publisher). subs.ass = what is burned in: callouts over SCREEN scenes only
    (plan_callouts; colour chosen per callout from the luminance of the rendered clip under it) + the
    affiliate overlay. Needs the SCREEN clips already rendered (scene.clip)."""
    fps = cfg["video"]["fps"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    P = plan_phrases(scenes)
    srt = []
    for n, p in enumerate(P, 1):
        srt_txt = "\n".join(_sub_text(ln) for ln in p["lines"])
        srt.append(f"{n}\n{_ts_srt(p['s0'])} --> {_ts_srt(p['s1'])}\n{srt_txt}\n")
    callouts = plan_callouts(P, scenes, fps)
    events = []
    for c in callouts:
        if c.get("skipped"):
            continue
        box = callout_box(c["text"], W, H)
        if c["clip"]:
            zs = zone_luminance(Path(c["clip"]), c["s0"] - c["shot_t0"], c["s1"] - c["shot_t0"], box,
                                _callout_baseline(H)[1])
            lums = [z["lum"] for z in zs]
            lum, dark_frac = float(np.median(lums)), float(np.mean([z["dark_frac"] for z in zs]))
        else:
            lums, lum, dark_frac = [], theme_paper.relative_luminance(theme_paper.palette()["bg"]), 0.0
            c["flags"].append("no rendered clip: assumed the paper background")
        col = callout_colors(lum)
        minority = dark_frac if col["zone"] == "light" else 1 - dark_frac
        if minority > 0.10:
            c["flags"].append(f"mixed zone: {minority:.0%} of the callout box is {'dark' if col['zone'] == 'light' else 'light'}"
                              f" (a card edge runs under the text)")
        c.update(box=box, luminance=round(lum, 4), luminance_samples=lums, dark_frac=round(dark_frac, 3), colors=col)
        events.append(callout_event(c))
    C = caption_ass_colors()
    for sc in scenes:
        if sc.overlay:
            s0, s1 = sc.narr_start_frame / fps, (sc.narr_start_frame + sc.narr_frames) / fps
            events.append(f"Dialogue: 1,{_ts_ass(s0)},{_ts_ass(s1)},Overlay,,0,0,0,,{_clean(sc.overlay)}")
    styles = [ass_style("Callout", CALLOUT_FONT_KEY, CALLOUT_SIZE, C["callout_text"], C["callout_keyword"], 2,
                        CALLOUT_MARGIN_H, CALLOUT_MARGIN_V),
              ass_style("Overlay", SUB_FONT_KEY, OVERLAY_SIZE, C["callout_text"], C["callout_keyword"], 9, 60, 50)]
    ass_path.write_text(ass_header(W, H, styles) + "\n".join(events) + "\n", encoding="utf-8")
    srt_path.write_text("\n".join(srt), encoding="utf-8")
    shown = [c for c in callouts if not c.get("skipped")]
    info = {"phrases": len(P), "merged_short_phrases": P[0]["merges_total"] if P else 0,
            "lead_ms": int(SUB_LEAD_S * 1000), "min_phrase_s": SUB_MIN_PHRASE_S,
            "gap_fill_s": SUB_GAP_FILL_S, "ended_early_for_next_lead": P[0]["clipped_total"] if P else 0,
            "srt": {"content": "full transcript (closed captions; Publisher captions.insert, language en)",
                    "max_line_chars": SUB_LINE_CHARS, "max_lines": 2, "line_width_px": SUB_MAX_W_PX,
                    "two_line_events": sum(1 for p in P if len(p["lines"]) == 2),
                    "kept_short_phrases": P[0]["kept_short_total"] if P else 0,
                    "rule_flags": sum(1 for p in P if p["flags"])},
            "burned": {"policy": "long-form: callouts over SCREEN scenes only; no burned transcript, nothing over "
                                 "EXPLAIN",
                       "font": theme_paper.FONT_FACES[CALLOUT_FONT_KEY],
                       "font_file": Path(theme_paper.FONT_FILES[CALLOUT_FONT_KEY]).name, "size_ass": CALLOUT_SIZE,
                       "line_box_bottom_y": H - CALLOUT_MARGIN_V, "max_width_px": CALLOUT_MAX_W_PX,
                       "style": f"BorderStyle 1, Outline 0, Shadow {theme_paper.CAPTION_SHADOW['px']} (no box); "
                                f"shadow {C['hex']['shadow']} @ {C['hex']['shadow_alpha']:g}",
                       "colors": {k: v for k, v in C["hex"].items() if k.startswith("callout") or k == "shadow"}},
            "callouts": [{k: c[k] for k in ("phrase", "scene", "kind", "s0", "s1", "source", "text", "flags")}
                         | {k: c[k] for k in ("luminance", "luminance_samples", "dark_frac", "colors") if k in c}
                         | ({"skipped": True} if c.get("skipped") else {}) for c in callouts],
            "callouts_shown": len(shown),
            "overlays": sum(1 for s in scenes if s.overlay)}
    return info, P


# ---------------------------------------------------------------- informe de sincronía

def _speech_edges(wav: Path, hop_s: float = 0.01, thr_db: float = -40.0, min_sil_s: float = 0.06):
    """Speech onsets and offsets by energy (independent of Whisper)."""
    audio, sr = sf.read(str(wav), dtype="float32")
    hop = int(sr * hop_s)
    n = len(audio) // hop
    rms = np.sqrt(np.mean(audio[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    speech = 20 * np.log10(rms) > thr_db
    k = int(round(min_sil_s / hop_s))
    onsets, offsets = [], []
    for i in range(k, n):
        if speech[i] and not speech[i - k:i].any():
            onsets.append(i * hop_s)
    for i in range(0, n - k):
        if speech[i] and not speech[i + 1:i + 1 + k].any():
            offsets.append((i + 1) * hop_s)
    return np.array(onsets), np.array(offsets)


def _nearest(arr: np.ndarray, t: float, win: float = 0.4):
    if arr.size == 0:
        return None
    j = int(np.argmin(np.abs(arr - t)))
    return float(arr[j]) if abs(arr[j] - t) <= win else None


def subtitle_report(P: list[dict], scenes: list, narration: Path, out_md: Path, flag_ms: int = 200,
                    callouts: list[dict] | None = None) -> dict:
    """Sync check of final.srt (alignment table) + the burned-in callouts table."""
    onsets, offsets = _speech_edges(narration)
    nonw = {}
    for sc in scenes:
        for w in sc.word_report:
            if w["method"] != "whisper":
                nonw.setdefault(sc.index, []).append(w)
    rows, flagged, d_in_all = [], 0, []
    for n, p in enumerate(P, 1):
        on, off = _nearest(onsets, p["a0"]), _nearest(offsets, p["a1"])
        d_in = None if on is None else round((p["a0"] - on) * 1000)
        d_out = None if off is None else round((p["a1"] - off) * 1000)
        lead = round((p["a0"] - p["s0"]) * 1000)
        hold = round((p["s1"] - p["a1"]) * 1000)
        ref_in = on if on is not None else p["a0"]
        ref_out = off if off is not None else p["a1"]
        early_ms = round((ref_in - p["s0"]) * 1000)      # cuánto antes aparece respecto a la voz real
        late_ms = round((p["s1"] - ref_out) * 1000)      # negativo: desaparece antes de que acabe la voz
        words_in = [f"{w['word']}@{w['start']:.2f}" for sc_i in p["scenes"] for w in nonw.get(sc_i, [])
                    if any(u.display == w["word"] for u in p["units"])]
        problems = []
        if d_in is not None and abs(d_in) > flag_ms:
            problems.append(f"Whisper start vs voice {d_in:+d} ms")
        if d_out is not None and abs(d_out) > flag_ms:
            problems.append(f"Whisper end vs voice {d_out:+d} ms")
        if early_ms < 0:
            problems.append(f"appears {-early_ms} ms LATE")
        if late_ms < -flag_ms:
            problems.append(f"leaves {-late_ms} ms before the voice ends")
        if problems:
            flagged += 1
        if d_in is not None:
            d_in_all.append(abs(d_in))
        text = " ".join(u.display for u in p["units"]).replace("|", "/")
        rows.append(f"| {n} | {text} | {p['s0']:.2f} | {p['s1']:.2f} | {p['a0']:.2f} | {p['a1']:.2f} | "
                    f"{'—' if on is None else f'{on:.2f}'} | {'—' if off is None else f'{off:.2f}'} | "
                    f"{lead} | {hold} | {'; '.join(words_in) or ''} | {'**' + '; '.join(problems) + '**' if problems else 'ok'} |")
    head = f"""# subtitle_check

Generated by the Producer. Times in seconds of the video. The table below validates **final.srt** (the
full transcript, uploaded as closed captions); the long-form video only burns in the callouts listed at
the end.

- **sub in/out**: when the subtitle appears and disappears.
- **audio in/out (Whisper)**: first and last word of the phrase according to the alignment.
- **voice in/out (energy)**: speech start/end measured on the narration by energy (threshold −40 dBFS,
  silence ≥ 60 ms). "—" = the phrase starts or ends without a pause (mid-sentence), so there is no
  edge to measure. Note: word edges that fall in a pause were already snapped to this same
  energy (align.refine_with_energy), so Δ≈0 there by construction; what this table still
  catches are phrases whose Whisper start is not in a pause, interpolations and cuts caused by the lead.
- **lead**: ms the subtitle appears ahead of its audio (target 100–150). **hold**: ms it stays
  after the last word (≥ 0; more if it fills a short gap).
- **words without Whisper**: time replaced or interpolated (check by ear at that second).
- Every difference > {flag_ms} ms between Whisper and the measured voice is flagged, as is a subtitle
  that appears late or leaves before the voice ends.

**Phrases:** {len(P)} · **flagged:** {flagged} · **mean |Δ start| Whisper vs voice:** {round(float(np.mean(d_in_all))) if d_in_all else '—'} ms (n={len(d_in_all)})

| # | phrase | sub in | sub out | audio in | audio out | voice in | voice out | lead ms | hold ms | words without Whisper | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    out_md.write_text(head + "\n".join(rows) + "\n" + callout_markdown(callouts or []), encoding="utf-8")
    return {"phrases": len(P), "flagged": flagged,
            "mean_abs_start_delta_ms": round(float(np.mean(d_in_all))) if d_in_all else None,
            "measured_starts": len(d_in_all)}


def callout_markdown(callouts: list[dict]) -> str:
    """'Callouts' section of subtitle_check.md: what is burned in over SCREEN scenes and why that colour."""
    head = f"""
## Callouts (burned in)

Long-form policy: no burned transcript; one callout per phrase with a *keyword* (or a `[CALLOUT: ...]`)
while a SCREEN scene is on screen; nothing over EXPLAIN. Colour per callout from the rendered clip under
the callout ({CALLOUT_SAMPLES} frames): luminance = WCAG relative luminance of the median pixel between cap
height and baseline; text #0B1220 or #F8FAFC, whichever contrasts more; keyword in accent unless < 3:1
there. "dark %" = share of the ink box (descenders included) on a dark zone; a minority > 10 % is flagged
as a mixed zone (a card edge under the text).

**Callouts:** {sum(1 for c in callouts if not c.get('skipped'))} shown · {sum(1 for c in callouts if c.get('skipped'))} skipped

| # | in | out | scene | source | callout | luminance | dark % | zone | text | keyword (contrast) | flags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    rows = []
    for c in callouts:
        col = c.get("colors") or {}
        rows.append(f"| {c['phrase']} | {c['s0']:.2f} | {c['s1']:.2f} | {c['scene']} {c['kind']} | {c['source']} | "
                    f"{c['text'].replace('|', '/')} | {c.get('luminance', '—')} | "
                    f"{round(c['dark_frac'] * 100) if 'dark_frac' in c else '—'} | {col.get('zone', '—')} | "
                    f"{col.get('text', '—')} | {col.get('keyword', '—')} ({col.get('contrast_keyword', '—')}) | "
                    f"{'; '.join(c['flags']) or 'ok'} |")
    return head + "\n".join(rows) + "\n"


# ---------------------------------------------------------------- audio de los clips (efectos)
# Cada clip puede traer una pista 48 kHz estéreo con SOLO sus efectos (sfx.place, a ganancia unitaria) o
# el audio propio de explainroo; si no trae audio cuenta como silencio. El ensamblaje la pone en su sitio
# con precisión de muestra y la mezcla 18 dB por debajo de la voz (theme_paper.SFX).

AUDIO_SR = 48000
CLIP_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_SR), "-ac", "2"]
# BS.1770-4: ponderación K a 48 kHz (estante + paso alto), coeficientes de la norma: (b0, b1, b2, a1, a2)
_K_SOS = ((1.53512485958697, -2.69169618940638, 1.19839281085285, -1.69065929318241, 0.73248077421585),
          (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621))
_K_IR: list = []
SFX_EVENT_THR_DB = -60.0       # un "evento" es un tramo con muestras > −60 dBFS...
SFX_EVENT_GAP_S = 0.10         # ...y huecos menores de 100 ms dentro de él
SFX_EDGE_S = 0.003             # rampa de ganancia a cada lado de un evento al nivelarlo


def clip_samples(frames: int, fps: int) -> int:
    """48 kHz audio samples of a clip of `frames` frames (at 30 fps: exactly 1600 per frame)."""
    return int(round(frames * AUDIO_SR / fps))


def clip_audio_filter(n: int) -> str:
    """-af chain that turns any audio into 48 kHz stereo with exactly `n` samples (pads with
    silence or trims)."""
    return (f"aresample={AUDIO_SR},aformat=sample_fmts=fltp:sample_rates={AUDIO_SR}:channel_layouts=stereo,"
            f"apad=whole_len={n},atrim=end_sample={n}")


def has_audio(path: Path) -> bool:
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, creationflags=_NOWIN)
    return bool(p.stdout.strip())


def add_clip_audio(clip: Path, frames: int, fps: int, audio: Path | None = None) -> Path:
    """For renderers: puts into `clip` (already encoded video, copied without re-encoding) a 48 kHz
    stereo track of exactly its duration: `audio` (e.g. the sfx.place track) or silence. Replaces the
    file. Without calling it, a clip with no audio is fine too: assembly treats it as silence."""
    n = clip_samples(frames, fps)
    src = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", f"anullsrc=r={AUDIO_SR}:cl=stereo"]
    tmp = clip.with_name(clip.stem + ".audio.mp4")
    ffmpeg(["-i", str(clip), *src, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", clip_audio_filter(n),
            *CLIP_AUDIO_ARGS, str(tmp)])
    os.replace(tmp, clip)
    return clip


def _clip_audio(clip: Path, n: int) -> np.ndarray | None:
    """The clip's audio as float32 (n, 2) at 48 kHz, exactly n samples; None if it has no audio."""
    if not has_audio(clip):
        return None
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-map", "0:a:0", "-af", clip_audio_filter(n),
                        "-f", "f32le", "-"], capture_output=True, creationflags=_NOWIN)
    if p.returncode != 0:
        raise RuntimeError(f"could not read the audio of {clip}: {p.stderr.decode('utf-8', 'replace')[-400:]}")
    a = np.frombuffer(p.stdout, np.float32).reshape(-1, 2)
    if len(a) != n:                    # atrim/apad ya lo garantizan; red de seguridad
        a = np.pad(a, ((0, max(0, n - len(a))), (0, 0)))[:n]
    return a


def _k_ir() -> np.ndarray:
    """Impulse response (0.5 s) of the K filter: allows FFT filtering without scipy."""
    if not _K_IR:
        x = [1.0] + [0.0] * (AUDIO_SR // 2 - 1)
        for b0, b1, b2, a1, a2 in _K_SOS:
            y, x1, x2, y1, y2 = [], 0.0, 0.0, 0.0, 0.0
            for v in x:
                o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
                x2, x1, y2, y1 = x1, v, y1, o
                y.append(o)
            x = y
        _K_IR.append(np.array(x))
    return _K_IR[0]


def momentary_max_lufs(a: np.ndarray) -> float:
    """Maximum momentary loudness (EBU R128 "M": BS.1770 K-weighting, 400 ms window) of a
    segment (n, channels) at 48 kHz. It is what a loudness meter shows when a short effect plays."""
    a = np.asarray(a, np.float64).reshape(len(a), -1)
    w = int(0.4 * AUDIO_SR)
    x = np.concatenate([np.zeros((w, a.shape[1])), a, np.zeros((w, a.shape[1]))])
    h = _k_ir()
    nfft = 1 << (len(x) + len(h) - 2).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nfft, axis=0) * np.fft.rfft(h, nfft)[:, None], nfft, axis=0)[:len(x)]
    c = np.concatenate([[0.0], np.cumsum((y ** 2).sum(axis=1))])
    ms = float((c[w:] - c[:-w]).max()) / w
    return -0.691 + 10 * np.log10(ms) if ms > 0 else float("-inf")


def sfx_events(a: np.ndarray) -> list[tuple[int, int]]:
    """Spans [start, end) with signal: samples > SFX_EVENT_THR_DB, joining gaps < SFX_EVENT_GAP_S."""
    idx = np.flatnonzero(np.abs(a).max(axis=1) > 10 ** (SFX_EVENT_THR_DB / 20))
    if not idx.size:
        return []
    cut = np.flatnonzero(np.diff(idx) > SFX_EVENT_GAP_S * AUDIO_SR)
    return list(zip(np.r_[idx[0], idx[cut + 1]].tolist(), (np.r_[idx[cut], idx[-1]] + 1).tolist()))


def integrated_lufs(path: Path) -> float:
    """Integrated loudness (gated BS.1770, FFmpeg's ebur128 filter) of the first audio track."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                        "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_NOWIN)
    m = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", p.stderr)
    if p.returncode != 0 or not m:
        raise RuntimeError(f"ebur128 could not measure {path}: {p.stderr.strip()[-300:]}")
    return float(m[-1])


def power_mean_db(values: list[float]) -> float:
    return float(10 * np.log10(np.mean([10 ** (v / 10) for v in values])))


def level_events(a: np.ndarray, target_m: float) -> tuple[np.ndarray, list[dict]]:
    """Brings EACH event of `a` (n, 2) to maximum momentary loudness = target_m (LUFS); outside the
    events it leaves digital silence. The gain change uses SFX_EDGE_S cosine ramps in the
    < −60 dBFS zone around the event (no clicks). Returns (leveled audio, [{i, j, m_in, gain_db}])."""
    env = np.zeros(len(a))
    e = int(SFX_EDGE_S * AUDIO_SR)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(1, e + 1) / (e + 1))
    out = []
    for i, j in sfx_events(a):
        m = momentary_max_lufs(a[i:j])
        g_db = target_m - m
        g = 10 ** (g_db / 20)
        env[i:j] = g
        k = min(e, i)
        env[i - k:i] = g * ramp[e - k:]
        k = min(e, len(a) - j)
        env[j:j + k] = g * ramp[::-1][:k]
        out.append({"i": i, "j": j, "m_in": m, "gain_db": g_db})
    return (a * env[:, None]).astype(np.float32), out


def build_sfx_track(shots: list, fps: int, out_wav: Path, target_m: float) -> dict:
    """Effects track for the whole video, already at its final level: each clip's audio in place with
    sample accuracy (boundaries = round(frame × 48000 / fps), no drift), silence for clips without
    audio, and each event brought to `target_m` (level_events). Per event rather than one global gain:
    explainroo normalizes EACH scene's soundtrack to −14 LUFS (video.json "loudness", two-pass
    loudnorm), so the same tick comes out louder or quieter depending on the scene and how many effects
    it has; clips using sfx.place arrive at unity gain. The audio of the stream-copy concat is not used:
    clips without audio would break it and each clip's AAC carries its own padding."""
    events, with_audio, cum, peak = [], 0, 0, 0.0
    with sf.SoundFile(str(out_wav), "w", AUDIO_SR, 2, "FLOAT") as f:
        for s in shots:
            a0, a1 = clip_samples(cum, fps), clip_samples(cum + s.frames, fps)
            cum += s.frames
            a = _clip_audio(Path(s.clip), a1 - a0)
            if a is None:
                f.write(np.zeros((a1 - a0, 2), np.float32))
                continue
            with_audio += 1
            y, evs = level_events(a, target_m)
            f.write(y)
            peak = max(peak, float(np.abs(y).max(initial=0.0)))
            for ev in evs:
                i, j = ev["i"], ev["j"]
                events.append({"t_s": round((a0 + i) / AUDIO_SR, 3), "dur_s": round((j - i) / AUDIO_SR, 3),
                               "scene": s.index, "m_in_lufs": round(ev["m_in"], 2), "gain_db": round(ev["gain_db"], 2),
                               "peak_in_dbfs": round(20 * np.log10(float(np.abs(a[i:j]).max())), 2)})
    return {"path": str(out_wav), "samples": clip_samples(cum, fps), "clips": len(shots),
            "clips_with_audio": with_audio, "events": events, "target_lufs_m": round(target_m, 2),
            "in_level_lufs_m": round(power_mean_db([e["m_in_lufs"] for e in events]), 2) if events else None,
            "peak_dbfs": round(20 * np.log10(peak), 2) if peak > 0 else None}


# ---------------------------------------------------------------- render final

def assemble(scenes: list, narration: Path, music: Path, ass: Path, cfg: dict, workdir: Path, out_mp4: Path) -> dict:
    """Stream-copy video concat + effects track (build_sfx_track) + burned-in callouts (subs.ass) + final mix:
    voice + music ducked under the voice (sidechain) + effects NOT ducked, each event with maximum
    momentary loudness (EBU R128 "M", 400 ms) = integrated loudness of the voice (BS.1770, narration.wav)
    + theme_paper.SFX["level_db_vs_voice"] (−18 dB); then the usual loudnorm (same gain
    for everything, so the balance is kept)."""
    v = cfg["video"]
    t0 = time.perf_counter()
    shots = [s for s in scenes if s.frames > 0]
    lst = workdir / "clips.txt"
    lst.write_text("".join(f"file '{Path(s.clip).as_posix()}'\n" for s in shots), encoding="utf-8")
    ffmpeg(["-f", "concat", "-safe", "0", "-i", lst.name, "-map", "0:v:0", "-c", "copy", "video_raw.mp4"],
           cwd=workdir)
    concat_s = time.perf_counter() - t0
    t_sfx = time.perf_counter()
    voice_lufs = integrated_lufs(narration)
    rel_db = theme_paper.SFX["level_db_vs_voice"]
    sfx = build_sfx_track(shots, v["fps"], workdir / "sfx_track.wav", voice_lufs + rel_db)
    sfx_s = time.perf_counter() - t_sfx
    copy_caption_fonts(workdir / "fonts", (CALLOUT_FONT_KEY, SUB_FONT_KEY))
    if Path(ass).resolve() != (workdir / "subs.ass").resolve():
        shutil.copy2(ass, workdir / "subs.ass")
    mc = cfg["music"]
    duck = (f"sidechaincompress=threshold={mc.get('duck_threshold', 0.015)}:ratio={mc.get('duck_ratio', 10)}"
            f":attack={mc.get('duck_attack_ms', 15)}:release={mc.get('duck_release_ms', 800)}")
    fmt = f"aresample={AUDIO_SR},aformat=sample_fmts=fltp:sample_rates={AUDIO_SR}:channel_layouts=stereo"
    graph = (
        f"[0:v]{burn_filter('subs.ass', 'fonts')},format=yuv420p[v];"
        f"[1:a]{fmt},asplit=2[voice][sc];"
        f"[2:a]{fmt},volume={mc.get('volume', 0.22)}[mus];"
        f"[mus][sc]{duck}[duck];"
    )
    inputs = ["-i", "video_raw.mp4", "-i", str(narration), "-stream_loop", "-1", "-i", str(music)]
    if not sfx["events"]:
        graph += "[voice][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    else:
        inputs += ["-i", "sfx_track.wav"]      # ya nivelada: entra a 0 dB y sin sidechain
        graph += (f"[3:a]{fmt}[sfx];"
                  "[voice][duck][sfx]amix=inputs=3:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    t1 = time.perf_counter()
    ffmpeg([*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", v["preset"], "-crf", str(v["crf"]), "-r", str(v["fps"]), *COLOR_ARGS,
            "-c:a", "aac", "-b:a", "192k", "-ar", str(AUDIO_SR), "-shortest", "-movflags", "+faststart",
            str(out_mp4)], cwd=workdir)
    return {"shots": len(shots), "concat_s": round(concat_s, 2), "encode_s": round(time.perf_counter() - t1, 2),
            "encoder": f"libx264 preset={v['preset']} crf={v['crf']}", "audio": "aac 192k 48 kHz, loudnorm -14 LUFS",
            "music_ducking": duck,
            "sfx": {"events": len(sfx["events"]), "clips_with_audio": sfx["clips_with_audio"],
                    "voice_integrated_lufs": voice_lufs, "target_db_vs_voice": rel_db,
                    "target_lufs_m": sfx["target_lufs_m"], "in_level_lufs_m": sfx["in_level_lufs_m"],
                    "track_peak_dbfs": sfx["peak_dbfs"], "ducked": False,
                    "method": "per event (> −60 dBFS, gaps < 100 ms joined): max momentary loudness "
                              "(400 ms, K-weighted) = voice integrated loudness (BS.1770, ebur128) − 18 dB",
                    "seconds": round(sfx_s, 2), "detail": sfx["events"][:200]}}


def content_scan(path: Path, step: float = 0.5, min_frac: float = 0.01, warn_s: float = 1.0) -> dict:
    """'Empty picture' stretches: every `step` s, measures what fraction of the top PANEL_FRAC (80 %) of
    the frame has content (pixels that differ from that frame's background by > 25 luma levels).
    Stretches with < `min_frac` lasting >= `warn_s` are reported as warnings (the 2026-11-16 human
    review asked for none)."""
    W_, H_ = 480, 270
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={1 / step},scale={W_}:{H_}",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True, creationflags=_NOWIN)
    fr = np.frombuffer(p.stdout, np.uint8).reshape(-1, H_, W_).astype(np.int16)[:, : int(H_ * PANEL_FRAC)]
    bg = np.median(fr.reshape(len(fr), -1), axis=1)[:, None, None]
    content = (np.abs(fr - bg) > 25).mean(axis=(1, 2))
    stretches, start = [], None
    for i, c in enumerate(list(content) + [1.0]):
        if c < min_frac and start is None:
            start = i
        elif c >= min_frac and start is not None:
            stretches.append({"from_s": round(start * step, 1), "to_s": round(i * step, 1),
                              "min_content_pct": round(float(content[start:i].min()) * 100, 2)})
            start = None
    warn = [s for s in stretches if s["to_s"] - s["from_s"] >= warn_s]
    return {"samples": int(len(content)), "median_content_pct": round(float(np.median(content)) * 100, 1),
            "near_empty": stretches, "near_empty_warnings": warn}


def probe(path: Path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
                        "-of", "json", str(path)], capture_output=True, text=True, creationflags=_NOWIN)
    j = json.loads(p.stdout)
    vs = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    return {"duration_s": round(float(j["format"]["duration"]), 3), "size_mb": round(int(j["format"]["size"]) / 2**20, 1),
            "video": f"{vs['codec_name']} {vs['width']}x{vs['height']} @ {vs['r_frame_rate']}",
            "audio": a.get("codec_name"), "width": vs["width"], "height": vs["height"], "fps": vs["r_frame_rate"]}

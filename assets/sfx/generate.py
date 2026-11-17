"""Genera assets/sfx/{tick,pop,swoosh}.wav (síntesis propia, dominio público / CC0).

Uso (desde la raíz del proyecto):  python assets/sfx/generate.py
Determinista (semilla fija). 48 kHz, estéreo, PCM 16 bits. Ataque y final con fundidos coseno (sin clics).
Calibración: los tres quedan con la MISMA sonoridad momentánea máxima (EBU R128 «M», 400 ms, la medida
que usa el ensamblaje para colocarlos 18 dB bajo la voz) y el de pico más alto queda en −3 dBFS.
Así cualquier mezcla de eventos cae al mismo nivel y la relación tick/pop/swoosh no depende del video.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from producer.assemble import momentary_max_lufs  # noqa: E402

SR = 48000
PEAK_DBFS = -3.0
OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(20261116)


def t_axis(dur: float) -> np.ndarray:
    return np.arange(int(round(dur * SR))) / SR


def fades(x: np.ndarray, fin: float, fout: float) -> np.ndarray:
    """Fundidos de medio coseno al inicio y al final (evitan el clic de un corte en seco)."""
    n_in, n_out = int(fin * SR), int(fout * SR)
    env = np.ones(len(x))
    env[:n_in] = 0.5 - 0.5 * np.cos(np.pi * np.arange(n_in) / n_in)
    env[len(x) - n_out:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(n_out) / n_out)
    return x * (env if x.ndim == 1 else env[:, None])


def one_pole_lp(x: np.ndarray, fc: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * fc / SR)
    y, s = np.empty_like(x), 0.0
    for i, v in enumerate(x):
        s = (1 - a) * v + a * s
        y[i] = s
    return y


def tick() -> np.ndarray:
    """55 ms: «tic» de tecla suave. Cuerpo 950 Hz + 1900/2850 Hz que decaen rápido (τ 7–12 ms) y un
    soplo de ruido de 4 ms pasado por paso bajo (la textura del golpe, sin chasquido)."""
    t = t_axis(0.055)
    x = (0.30 * np.sin(2 * np.pi * 950 * t) * np.exp(-t / 0.012)
         + 0.55 * np.sin(2 * np.pi * 1900 * t) * np.exp(-t / 0.009)
         + 0.20 * np.sin(2 * np.pi * 2850 * t) * np.exp(-t / 0.007))
    noise = one_pole_lp(rng.standard_normal(len(t)), 3500) * np.exp(-t / 0.004)
    x = x + 0.35 * noise / np.abs(noise).max()
    x = fades(x, 0.0015, 0.012)
    return np.stack([x, x], axis=1)


def pop() -> np.ndarray:
    """100 ms: «pop» de burbuja. Senoide que sube de 380 a 820 Hz en 25 ms (glissando exponencial) y se
    apaga (τ 22 ms), con un 2.º armónico suave."""
    t = t_axis(0.100)
    f = 380 * (820 / 380) ** np.minimum(t / 0.025, 1.0)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * np.exp(-t / 0.022)
    x = fades(x, 0.002, 0.015)
    return np.stack([x, x], axis=1)


def swoosh() -> np.ndarray:
    """400 ms: ruido blanco por un resonador de 2 polos cuyo centro barre 350 → 3500 Hz (exponencial,
    Q≈1,3), mezclado con su paso bajo (cuerpo); envolvente seno² con el máximo al 65 %; paneo suave de
    izquierda a derecha (±30 %)."""
    dur = 0.400
    t = t_axis(dur)
    n = len(t)
    noise = rng.standard_normal(n)
    fc = 350 * (3500 / 350) ** (t / dur)
    q = 1.3
    y, x1, x2, y1, y2 = np.empty(n), 0.0, 0.0, 0.0, 0.0
    for i in range(n):                                  # paso banda de 2 polos variable (RBJ, pico 0 dB)
        w = 2 * np.pi * fc[i] / SR
        alpha = np.sin(w) / (2 * q)
        a0 = 1 + alpha
        b0 = alpha / a0                                 # b1 = 0, b2 = −b0
        a1, a2 = -2 * np.cos(w) / a0, (1 - alpha) / a0
        v = noise[i]
        o = b0 * v - b0 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y[i] = o
    body = one_pole_lp(noise, 600)
    x = y / np.abs(y).max() + 0.25 * body / np.abs(body).max()
    peak_at = 0.65
    u = t / dur
    env = np.where(u < peak_at, np.sin(0.5 * np.pi * u / peak_at) ** 2,
                   np.cos(0.5 * np.pi * (u - peak_at) / (1 - peak_at)) ** 2)
    x = fades(x * env, 0.010, 0.020)
    pan = 0.5 + 0.3 * (u - 0.5) * 2                     # 0.2 (izq.) -> 0.8 (der.)
    L, R = np.cos(0.5 * np.pi * pan), np.sin(0.5 * np.pi * pan)
    return np.stack([x * L, x * R], axis=1) * np.sqrt(2)


def spectrum(x: np.ndarray) -> dict:
    """Pico espectral, centroide y banda a −10 dB del pico (canal medio)."""
    m = x.mean(axis=1)
    X = np.abs(np.fft.rfft(m * np.hanning(len(m)), 1 << 16))
    f = np.fft.rfftfreq(1 << 16, 1 / SR)
    db = 20 * np.log10(X / X.max() + 1e-12)
    band = f[db > -10]
    return {"peak_hz": round(float(f[X.argmax()])), "centroid_hz": round(float((f * X ** 2).sum() / (X ** 2).sum())),
            "band_-10dB_hz": [round(float(band.min())), round(float(band.max()))]}


def main() -> None:
    raw = {"tick": tick(), "pop": pop(), "swoosh": swoosh()}
    # cada uno a pico −3 dBFS; luego todos bajan a la M del más flojo (el de pico más alto sigue en −3)
    peak = 10 ** (PEAK_DBFS / 20)
    raw = {k: v * peak / np.abs(v).max() for k, v in raw.items()}
    m_at_peak = {k: momentary_max_lufs(v) for k, v in raw.items()}
    target = min(m_at_peak.values())
    report = {}
    for k, v in raw.items():
        x = v * 10 ** ((target - m_at_peak[k]) / 20)
        path = OUT / f"{k}.wav"
        sf.write(str(path), x.astype(np.float32), SR, subtype="PCM_16")
        y, _ = sf.read(str(path), dtype="float64", always_2d=True)     # medir lo que quedó en disco
        k_w = y.mean(axis=1)
        report[k] = {"file": path.name, "duration_ms": round(len(y) / SR * 1000, 1),
                     "peak_dbfs": round(20 * np.log10(np.abs(y).max()), 2),
                     "rms_dbfs": round(10 * np.log10(np.mean(k_w ** 2)), 2),
                     "momentary_max_lufs": round(momentary_max_lufs(y), 2),
                     "first_last_sample": [round(float(np.abs(y[0]).max()), 5), round(float(np.abs(y[-1]).max()), 5)],
                     **spectrum(y)}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

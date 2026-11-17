# Efectos de sonido del tema "paper"

**Generados en casa** el 2026-11-16 con `generate.py` (numpy, síntesis pura, semilla fija): sin
grabaciones ni muestras de terceros. Se dedican al **dominio público (CC0 1.0)**.
Regenerar: `python assets/sfx/generate.py` (desde la raíz; imprime las medidas de abajo).

Formato: WAV 48 kHz, estéreo, PCM 16 bits. Ataque y final con fundidos de medio coseno (la primera y la
última muestra valen 0: sin clics). Uso (theme_paper.SFX["rules"]): tick al terminar un typewriter,
swoosh al entrar una tarjeta, pop al terminar una cifra.

| archivo | dur. | pico | RMS | M máx. (EBU R128, 400 ms) | espectro |
| --- | --- | --- | --- | --- | --- |
| tick.wav | 55 ms | −3,0 dBFS | −19,8 dBFS | −23,6 LUFS | pico 1,9 kHz; banda −10 dB 0,93–1,93 kHz; centroide 1,5 kHz |
| pop.wav | 100 ms | −7,3 dBFS | −20,0 dBFS | −23,6 LUFS | casi senoidal: 800–840 Hz (glissando 380→820 Hz en 25 ms) |
| swoosh.wav | 400 ms | −11,4 dBFS | −28,8 dBFS | −23,6 LUFS | ruido de banda ancha 0–4,7 kHz, centroide 2,5 kHz, barrido 350→3500 Hz |

Medidas comprobadas también con `ffmpeg -af ebur128` (M máx. −23,6 en los tres).

## Recetas

- **tick**: senoides 950 Hz (τ 12 ms) + 1900 Hz (τ 9 ms) + 2850 Hz (τ 7 ms) y un soplo de ruido de 4 ms
  por un paso bajo de 3,5 kHz. Fundidos 1,5 ms / 12 ms.
- **pop**: senoide con glissando exponencial 380 → 820 Hz en 25 ms, 2.º armónico al 18 %, decaimiento
  τ 22 ms. Fundidos 2 ms / 15 ms.
- **swoosh**: ruido blanco por un paso banda RBJ de 2 polos (Q 1,3) cuyo centro barre 350 → 3500 Hz
  (exponencial) + 25 % del mismo ruido por un paso bajo de 600 Hz; envolvente seno² con máximo al 65 %;
  paneo de izquierda (0,2) a derecha (0,8) con ley de potencia constante. Fundidos 10 ms / 20 ms.

## Calibración

Los tres tienen la **misma sonoridad momentánea máxima** (−23,6 LUFS), y el de pico más alto (tick)
queda en −3 dBFS; por eso pop y swoosh no llegan a −3 dBFS de pico. Es la medida que usa el ensamblaje:
`assemble.build_sfx_track` lleva cada evento a M máx. = sonoridad integrada de la voz − 18 dB
(theme_paper.SFX["level_db_vs_voice"]), así que el nivel absoluto de estos archivos no cambia el
resultado; la calibración solo hace que suenen parejos si alguien los usa sin ese paso.

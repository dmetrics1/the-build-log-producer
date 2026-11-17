# Fuentes del tema "paper"

Instancias **estáticas** creadas el 2026-11-16 (Inter-Bold, para el karaoke de los Shorts, la tarde del mismo
día, del mismo variable: sha256 idéntico) a partir de las fuentes variables oficiales del
repositorio `google/fonts` (rama `main`). Licencia: **SIL Open Font License 1.1** (textos completos en
`OFL-*.txt`; ninguna declara *Reserved Font Name*). Rutas y nombres: `src/producer/theme_paper.py`
(`FONT_FILES`, `FONT_FACES`).

| archivo | familia (name ID 1) / estilo | peso | origen (variable) | ejes fijados | KB |
| --- | --- | --- | --- | --- | --- |
| Inter-Regular.ttf | Inter / Regular | 400 | `ofl/inter/Inter[opsz,wght].ttf` | opsz 14, wght 400 | 334 |
| Inter-Medium.ttf | Inter Medium / Regular | 500 | idem | opsz 14, wght 500 | 334 |
| Inter-SemiBold.ttf | Inter SemiBold / Regular | 600 | idem | opsz 14, wght 600 | 335 |
| Inter-Bold.ttf | Inter / Bold | 700 | idem | opsz 14, wght 700 | 335 |
| SpaceGrotesk-Medium.ttf | Space Grotesk Medium / Regular | 500 | `ofl/spacegrotesk/SpaceGrotesk[wght].ttf` | wght 500 | 86 |
| SpaceGrotesk-Bold.ttf | Space Grotesk / Bold | 700 | idem | wght 700 | 86 |
| JetBrainsMono-Regular.ttf | JetBrains Mono / Regular | 400 | `ofl/jetbrainsmono/JetBrainsMono[wght].ttf` | wght 400 | 112 |
| JetBrainsMono-Bold.ttf | JetBrains Mono / Bold | 700 | idem | wght 700 | 112 |

URLs (raw):
- https://raw.githubusercontent.com/google/fonts/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf (+ `OFL.txt`)
- https://raw.githubusercontent.com/google/fonts/main/ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf (+ `OFL.txt`)
- https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf (+ `OFL.txt`)

sha256 (16) de los variables usados: Inter `29160a80ff49ddca`, Space Grotesk `acad6de1fc93436f`,
JetBrains Mono `48715a42ec242c21`. Los variables no se guardan en el repo (solo hacen falta las
instancias y las licencias).

## Cómo se crearon

fontTools 4.68 (`pip install fonttools`, solo para regenerarlas; el pipeline no lo necesita):

```python
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
f = instancer.instantiateVariableFont(TTFont("Inter[opsz,wght].ttf"), {"opsz": 14, "wght": 600},
                                      updateFontNames=True)   # nombres desde la tabla STAT
f.save("Inter-SemiBold.ttf")
```

`updateFontNames=True` deja nombres RIBBI: ID 1 = "Inter SemiBold", ID 2 = "Regular", ID 16/17 =
"Inter"/"SemiBold", usWeightClass = 600. En JetBrains Mono se corrigió el nombre PostScript (ID 6)
`JetBrainsMonoRoman-*` → `JetBrainsMono-*`. Inter con opsz 14 = el "Inter" de texto (el de Google Fonts
estático), no "Inter Display".

## libass (subtítulos quemados)

Verificado con FFmpeg 9.0.2 / libass 0.17.5 (`-v debug`, línea `fontselect`):
- `Fontname = Inter SemiBold`, `Bold = 0` → `Inter-SemiBold` (peso real 600, sin negrita sintética). ✔
- `Fontname = Inter`, `Bold = 600` o `-1` → elige `Inter-Regular` y lo engorda (libass solo empareja la
  familia por ID 1 / nombre completo). ✘ No usar.
- `Fontname = Inter`, `Bold = 1` con `Inter-Bold.ttf` en `fontsdir` → `fontselect: (Inter, 700, 0) ->
  Inter-Bold` (peso real 700; instancia RIBBI: ID 1 = "Inter", ID 2 = "Bold"). ✔ Karaoke de Shorts.
- `Inter-Bold.ttf` solo lo usa libass: no se copia a explainroo (`theme_paper.LIBASS_ONLY_FONTS`), así la
  clave de caché de las escenas EXPLAIN y SCREEN no cambia.

Métricas para el tamaño ASS: libass escala para que usWinAscent + usWinDescent = tamaño. Inter tiene
win 2269 + 660 sobre 2048 unidades: a tamaño 72, em = 50,3 px, mayúsculas 36,6 px.

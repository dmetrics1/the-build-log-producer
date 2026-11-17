# Origen de los tokens de marca

Copiados el 2026-11-16 desde el repositorio personal **dm-design-system** (versión 0.1.0):

| archivo | origen | sha256 (16) |
| --- | --- | --- |
| tokens.json | `dm-design-system/tokens/tokens.json` | d991b7c7d83c6667 |
| tokens.css | `dm-design-system/dist/tokens.css` (generado por su build/build.py) | 01bd3bf65bd9cb96 |

La fuente de verdad es `tokens.json`; `tokens.css` se guarda solo como referencia. El Productor lee
estos tokens a través de `src/producer/theme_paper.py` (tema claro `light` para el video, y la superficie
del tema oscuro `dark` para la terminal simulada). Para actualizar: volver a copiar ambos archivos desde el
repositorio de diseño y subir `theme_paper.VERSION`.

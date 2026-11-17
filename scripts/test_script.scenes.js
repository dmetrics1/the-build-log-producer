// Escenas EXPLAIN de scripts/test_script.md, en orden: x01 = primera [EXPLAIN], x02 = segunda...
// API: explainroo docs scene-api. Sin narración propia: los tiempos son segundos dentro de la
// escena (s.dur = duración medida de nuestra narración). El Productor antepone:
//   const SCENES = { xNN: { label, text, keywords: [...], braces: [...] } };
//   const METRICS = { display: {...}, values: {...}, ... } | null;
//   const THEME = { c: {...colores por función}, font, size, card, motion, sfx, frame, ... };
// SCENES trae los datos de la escena tomados del guion y METRICS las cifras medidas de la corrida
// de referencia, para que los números no queden fijos aquí. METRICS puede ser null (aún no hay
// corrida de referencia): entonces cada escena usa las llaves del guion o su valor de respaldo.
// THEME sale de src/producer/theme_paper.py (tema "paper", tokens DM): aquí NO hay colores, fuentes
// ni tiempos de animación escritos a mano.
//
// Ritmo (medido 2026-11-16 con fade_analyze; revisión humana: "partes parecen imágenes sueltas"):
//   - frame 0 nunca vacío (`at: -1` = ya estaba, sin entrada);
//   - la composición completa (cajas, iconos, etiquetas, ejes, pistas, ambas filas, ambas tarjetas,
//     flechas entre elementos ya presentes) está en pantalla a min(0,6 s, 0,25·dur): lay(s, f);
//   - con la narración solo llega el énfasis: color/estado "encendido" (emph), marcas de
//     annotate, tachados, llenado de barras, cifras y la frase final;
//   - ninguna entrada dura más de IN (THEME.motion.enter, 0,325 s; regla 250–400 ms ease-out).
// Tema paper (2026-11-16):
//   - títulos con máquina de escribir (THEME.motion.title_cps) desde t = 0; tick al terminar;
//   - tarjetas: rise (sube + fundido) y swoosh al entrar; contadores para cifras, pop al terminar;
//   - tachado animado en accent para listas "sin X"; terminal oscura con prompt ">" (35 ms/carácter);
//   - una palabra clave por frase en accent (*estrellas*); costos y advertencias en cost (accent3);
//   - el 20 % inferior (y > THEME.frame.subtitle_top = 864 px) queda libre para el subtítulo quemado.

const T = THEME;
const C = THEME.c;
const M = THEME.motion;
const F = THEME.font;
const Z = THEME.size;
const IN = M.enter;          // duración máxima de cualquier entrada
const FIRST = M.enter_min;   // entrada de los elementos de la composición
const at = (s, f) => Math.max(0, Math.min(s.dur - 0.3, s.dur * f));
// lay(s, f), f en 0..1: inicio de un elemento estructural; con dur ≤ IN termina antes de min(0,6, 0,25·dur)
const lay = (s, f) => Math.max(0, Math.min(0.6, 0.25 * s.dur) - IN) * f;
const data = (id) => (typeof SCENES !== 'undefined' && SCENES[id]) || { braces: [], keywords: [] };
const num = (str, fallback) => {
  const m = String(str || '').match(/[\d.]+/);
  return m ? parseFloat(m[0]) : fallback;
};
// metric('display.wall', respaldo): cifra medida de METRICS, o el respaldo si METRICS es null
// o no trae ese campo (o un número no válido).
const metric = (path, fallback) => {
  let v = typeof METRICS !== 'undefined' ? METRICS : null;
  for (const k of path.split('.')) {
    if (v === null || v === undefined || typeof v !== 'object') return fallback;
    v = v[k];
  }
  if (typeof fallback === 'number') return Number.isFinite(v) ? v : fallback;
  return v === null || v === undefined || v === '' ? fallback : String(v);
};

// ------------------------------------------------------------------ tema: fondo, sonido, piezas

// Fondo: cuadrícula de THEME.grid.px en THEME.c.grid sobre THEME.c.bg (el look es "plain"), y la
// sombra de tarjeta del tema (panel-shadow). El look de explainroo no acepta `shadow`; el motor la
// lee de s.theme.shadow en cada dibujo, así que se fija aquí (mismo valor en todas las escenas).
function paperBase(s) {
  try {
    s.theme.shadow = { color: T.card.shadow.color, blur: T.card.shadow.blur, y: T.card.shadow.y };
    s.theme.enter = { ...s.theme.enter, shape: M.card_enter, icon: M.card_enter };
  } catch (e) { /* sin acceso al tema: queda la sombra del look base */ }
  s.draw({ at: -1 }, (ctx) => {
    // Misma geometría que el fondo de los paneles SCREEN (screens.background): brillo radial con
    // centro en la esquina superior derecha (W-1, 0), radio THEME.c.glow_radius, alfa
    // THEME.c.glow_alpha·smoothstep(1 - d/R), debajo de la cuadrícula. Sin glow en el tema, no se dibuja.
    const glow = /^#[0-9a-f]{6}$/i.test(C.glow || '') ? C.glow : null;
    const ga = Number.isFinite(C.glow_alpha) ? C.glow_alpha : 0;
    const R = C.glow_radius > 0 ? C.glow_radius : 0.6 * s.W;
    if (glow && ga > 0) {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(glow.slice(i, i + 2), 16));
      const grad = ctx.createRadialGradient(s.W - 1, 0, 0, s.W - 1, 0, R);
      for (let k = 0; k <= 24; k++) {               // smoothstep muestreado (el canvas interpola lineal)
        const u = k / 24, t = 1 - u;
        grad.addColorStop(u, `rgba(${r},${g},${b},${(ga * t * t * (3 - 2 * t)).toFixed(4)})`);
      }
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, s.W, s.H);
    }
    // cuadrícula centrada como en los paneles: desfase (W mod paso)/2, (H mod paso)/2; líneas de 1 px
    const step = T.grid.px, ox = Math.floor((s.W % step) / 2), oy = Math.floor((s.H % step) / 2);
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = T.grid.width;
    ctx.beginPath();
    for (let x = ox; x < s.W; x += step) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, s.H); }
    for (let y = oy; y < s.H; y += step) { ctx.moveTo(0, y + 0.5); ctx.lineTo(s.W, y + 0.5); }
    ctx.stroke();
  });
}
const paper = (scenes) => Object.fromEntries(Object.entries(scenes).map(([id, fn]) => [id, (s) => { paperBase(s); fn(s); }]));

// cue: efecto propio (assets/sfx, a volumen unidad) en t; nada si el archivo no está, si t < 0
// (elemento que ya estaba) o si el mismo efecto sonó hace menos de 0,15 s en esta escena.
const _cues = new WeakMap();
function cue(s, name, t) {
  const src = T.sfx.files[name];
  if (!src || !(t >= 0) || t > s.dur - 0.05) return;
  const log = _cues.get(s) || [];
  if (log.some(([n, u]) => n === name && Math.abs(u - t) < 0.15)) return;
  log.push([name, t]);
  _cues.set(s, log);
  s.sound(src, { at: t, volume: T.sfx.volume, id: `${name}${log.length}` });
}

// texto con la palabra clave (*estrellas*) en accent
const tx = (s, str, o = {}) => s.text(str, { color: C.body, mark: C.keyword, ...o });
// título: Space Grotesk 700 a THEME.size.title, máquina de escribir desde `at` (0); tick al terminar
function title(s, str, o = {}) {
  const t0 = o.at ?? 0;
  const n = String(str).replace(/\*/g, '').length;
  s.text(str, { size: Z.title, font: F.title, color: C.title, mark: C.keyword, ...o, at: t0, enter: 'type', cps: M.title_cps, sfx: false });
  cue(s, T.sfx.rules.typewriter_end, t0 + n / M.title_cps);
}
// tarjeta: card-bg, borde card-border de THEME.card.border px, radio THEME.card.radius, sombra del
// tema; entra subiendo con fundido (rise) y suena swoosh. Con enter propio (p. ej. el "encendido"
// de emph, que funde) no suena.
const HOT = { stroke: C.accent, fill: C.accent_tint, iconColor: C.accent };
function card(s, label, o = {}) {
  const look = { fill: C.card_bg, stroke: C.card_border, width: T.card.border, radius: T.card.radius,
    textColor: C.title, iconColor: C.muted, enter: M.card_enter, dur: IN };
  if (o.enter === undefined) cue(s, T.sfx.rules.card_enter, s.time(o.at ?? 0));
  return s.box(label, { ...look, ...o });
}
const arrow = (s, a, b, o = {}) => s.arrow(a, b, { color: C.muted, labelColor: C.body, ...o });
// counter: cifra que cuenta desde 0 hasta la de `display` ("2.3 GB", "≈ 0.1¢") en THEME.motion.counter
// s, empezando en o.start (o max(0, at)); al terminar muestra `display` tal cual y suena pop. Con
// o.value y o.format cuenta ese valor con ese formato (p. ej. segundos -> "1 min 38 s"). Sin cifra
// (o con 0, como "$0") es texto fijo.
function counter(s, display, o = {}) {
  const { value: v0, format, start: st, ...rest } = o;
  const t0 = rest.at ?? 0;
  const start = st ?? Math.max(0, t0);
  const dur = M.counter;
  const m = String(display).match(/^([^\d]*?)(\d+(?:\.\d+)?)(\D*)$/);
  let value = Number.isFinite(v0) ? v0 : (m ? parseFloat(m[2]) : 0);
  let fmt = format;
  if (!fmt && m) {
    const dec = (m[2].split('.')[1] || '').length;
    fmt = (x) => `${m[1]}${x.toFixed(dec)}${m[3]}`;
  }
  const base = { font: F.mono, bold: true, color: C.kpi, dur: FIRST, ...rest };
  if (!fmt || !(value > 0)) return s.text(display, base);
  const p = s.ease.out(s.clamp((s.t - start) / dur, 0, 1));
  cue(s, T.sfx.rules.number_end, start + dur);
  return s.text(p >= 1 ? display : fmt(value * p), base);
}
// emph: un elemento entra neutro en `from` y su versión enfatizada (color, estado "encendido")
// aparece encima en T con un fundido de IN; la neutra se retira sin salida a mitad del fundido
// (check solo mide solapes de textos opacos). make(o) dibuja el elemento con las opciones o.
function emph(make, base, on, from, T2) {
  make({ ...base, at: from, dur: FIRST, out: T2 + IN / 2, exit: 'none' });
  return make({ ...base, ...on, id: base.id ? `${base.id}_on` : undefined, at: T2, dur: IN, enter: 'fade', sfx: false });
}

// Escala de las piezas de cifras (tarjeta de $0, marcador, barras de memoria): revisión del dueño
// 2026-11-16, ×1,3 en tamaños (letra, tarjetas, grosor de barra), no con zoom de cámara. Sale de
// THEME.size.figure_scale cuando el tema lo trae; 1,3 si no.
const K = (Z.figure_scale > 0 ? Z.figure_scale : 1.3);
const SUB = T.frame.subtitle_top;   // nada por debajo de esta y (subtítulo quemado)

// barra de memoria: pista y escala desde el frame 0; llenado y contador juntos (THEME.motion.counter).
// Todo el bloque (título, pista, etiquetas, cifra) va a escala K; el ancho de la barra se limita al
// área segura (las etiquetas de los extremos sobresalen media palabra).
function memBar(s, { value, valueText = `${value} GB`, max = 8, head, mark = null, color = C.accent }) {
  s.camera([]);
  const W = Math.min(1300 * K, s.safe.w - 4 * Z.mono), H = 96 * K, x0 = s.cx - W / 2, FILL0 = 0.05;
  // centro vertical: el bloque (título arriba, cifra abajo) queda centrado y sobre la banda de subtítulos
  const y = Math.min(s.cy + 30, SUB - 175 * K - 30);
  const v = Math.max(0, Math.min(max, value));
  s.draw({ at: -1, box: { x: s.cx, y, w: W, h: H } }, (ctx) => {
    const p = s.ease.out(s.clamp((s.t - FILL0) / M.counter, 0, 1));
    ctx.fillStyle = C.track;
    ctx.beginPath(); ctx.roundRect(x0, y - H / 2, W, H, T.card.radius); ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.roundRect(x0, y - H / 2, Math.max(2, W * (v / max) * p), H, T.card.radius); ctx.fill();
    if (mark != null) {
      const mx = x0 + (W * mark) / max;
      ctx.setLineDash([12 * K, 10 * K]); ctx.strokeStyle = C.title; ctx.lineWidth = 4 * K;
      ctx.beginPath(); ctx.moveTo(mx, y - H); ctx.lineTo(mx, y + H * 0.8); ctx.stroke(); ctx.setLineDash([]);
    }
  });
  title(s, head, { y: y - 250 * K, size: Z.title * K });
  s.text('0', { x: x0, y: y + 110 * K, size: Z.mono * K, font: F.mono, color: C.muted, at: -1 });
  s.text(`${max} GB`, { x: x0 + W, y: y + 110 * K, size: Z.mono * K, font: F.mono, color: C.muted, at: -1 });
  if (mark != null) tx(s, `limit *${mark} GB*`, { x: x0 + (W * mark) / max, y: y - 120 * K, size: Z.mono * K, at: lay(s, 0.3), dur: FIRST });
  // la cifra va bajo el extremo de la barra, sin tapar la etiqueta "0" (mono: ~0,6·size por carácter)
  const half = 0.3 * 60 * K * String(valueText).length;
  const cx = Math.max(x0 + (W * v) / max, x0 + half + Z.mono * K);
  counter(s, valueText, { x: cx, y: y + 130 * K, size: 60 * K, color, at: -1, start: FILL0 });
}

// barras horizontales: pistas y etiquetas desde el frame 0; llenado y contador juntos
function hbars(s, rows, max) {
  const W = 1100, x0 = 560, H = 80;
  rows.forEach((r, i) => {
    const y = s.cy - 90 + i * 180, t0 = 0.05 + i * 0.15;
    tx(s, r.label, { x: x0 - 40, y, size: Z.body, align: 'right', at: -1 });
    s.draw({ at: -1, box: { x: x0 + W / 2, y, w: W, h: H } }, (ctx) => {
      const p = s.ease.out(s.clamp((s.t - t0) / M.counter, 0, 1));
      ctx.fillStyle = C.track;
      ctx.beginPath(); ctx.roundRect(x0, y - H / 2, W, H, T.card.radius); ctx.fill();
      ctx.fillStyle = r.color;
      ctx.beginPath(); ctx.roundRect(x0, y - H / 2, Math.max(2, (W * r.value / max) * p), H, T.card.radius); ctx.fill();
    });
    counter(s, r.valueText, { x: x0 + (W * r.value) / max + 30, y, size: 48, align: 'left', color: r.color, at: -1, start: t0 });
  });
}

export default paper({
  // 0:00 hook: costo de software medido (METRICS.display.software); sin METRICS, la llave del guion
  x01(s) {
    s.camera([]);
    const software = metric('display.software', data('x01').braces[0] || '$0');
    // tarjeta blanca detrás de la cifra: el costo (accent3) llega a 3,2:1 sobre card-bg (2,9:1 sobre bg)
    // ×K: 860×560 -> 1118×728; centro subido para que el borde inferior quede sobre la banda de subtítulos
    const h = 560 * K, y = Math.min(s.cy + 20 * K, SUB - 6 - h / 2);
    card(s, '', { x: s.cx, y, w: 860 * K, h, overlap: true, at: -1 });
    counter(s, software, { y: y - 50 * K, size: 300 * K, color: C.cost, at: -1 });
    tx(s, 'software *cost*', { y: y + 190 * K, size: 64 * K, color: C.muted, mark: C.cost, at: lay(s, 0.5), dur: FIRST });
  },
  x02(s) {
    s.camera([]);
    s.icon('laptop', { id: 'lap', x: s.cx - 330, y: s.cy - 20, size: 280, color: C.accent2, at: -1 });
    emph((o) => card(s, '8 GB VRAM', o), { id: 'gpu', x: s.cx + 330, y: s.cy - 20, icon: 'cpu', size: 64 },
      HOT, lay(s, 0.3), at(s, 0.25));
    arrow(s, 'lap', 'gpu', { at: lay(s, 0.6), dur: FIRST });
    tx(s, 'RTX 5050 Laptop GPU', { y: s.cy + 250, size: 48, color: C.muted, at: lay(s, 1), dur: FIRST });
  },
  // pico de memoria medido (METRICS.values.vram_peak_gb); sin METRICS, 2.3. El límite de 3 GB es el del guion.
  x03(s) {
    const v = metric('values.vram_peak_gb', 2.3);
    memBar(s, { value: v, valueText: metric('display.vram_peak', `${v} GB`), mark: 3, head: 'GPU memory, *whole run*' });
  },

  // 0:10 what you will see
  x04(s) {
    s.camera([]);
    card(s, 'script.md', { id: 'a', x: 330, y: s.cy, icon: 'file-text', size: 52, at: -1 });
    card(s, 'final.mp4', { id: 'b', x: 1590, y: s.cy, icon: 'file-video', size: 52, at: lay(s, 0.3), dur: FIRST });
    arrow(s, 'a', 'b', { at: lay(s, 0.6), dur: FIRST });
    ['voice', 'timing', 'scenes', 'assembly'].forEach((l, i) => {
      const x = 690 + i * 180, f = lay(s, 0.6 + i * 0.13);
      s.circle({ x, y: s.cy, r: 14, color: C.muted, fill: C.card_bg, overlap: true, at: f, dur: FIRST });
      tx(s, l, { x, y: s.cy + 80, size: 36, color: C.muted, at: f, dur: FIRST });
      // énfasis: cada etapa se enciende con la narración
      s.circle({ x, y: s.cy, r: 14, color: C.accent, fill: C.accent, overlap: true, at: at(s, 0.2 + i * 0.08), dur: IN, enter: 'fade', sfx: false });
    });
    s.annotate('b', { type: 'box', color: C.accent, at: at(s, 0.6), dur: IN });
  },
  x05(s) {
    s.camera([]);
    const names = ['Researcher', 'Writer', 'Producer', 'Publisher', 'Analyst'];
    const icons = ['search', 'pen-line', 'clapperboard', 'upload', 'chart-line'];
    const xs = s.row(5, { width: 1560 });
    title(s, 'Five AI *agents*', { y: 220 });
    names.forEach((n, i) => {
      const base = { id: `a${i}`, x: xs[i], y: s.cy - 20, size: 120, bg: 'circle', color: C.muted, label: n, labelSize: 40, labelColor: C.body };
      if (i === 2) emph((o) => s.icon(icons[i], o), base, { color: C.accent, labelColor: C.accent }, lay(s, 0.5), at(s, 0.45));
      else s.icon(icons[i], { ...base, at: i ? lay(s, i / 4) : -1, dur: FIRST });
    });
    tx(s, '*tested today*', { x: xs[2], y: s.cy + 230, size: 44, bold: true, at: at(s, 0.6), dur: IN });
  },

  // 0:24 the voice: dos tarjetas, SCREEN (ya está) y EXPLAIN (entra y se enciende con "Explain")
  x06(s) {
    s.camera([]);
    const y = s.cy;
    card(s, '', { x: 600, y, w: 600, h: 480, overlap: true, at: -1 });
    s.icon('monitor-play', { x: 600, y: y - 90, size: 180, color: C.accent2, at: -1 });
    s.text('SCREEN', { x: 600, y: y + 90, size: 72, font: F.title, color: C.title, at: 0, dur: FIRST });
    tx(s, 'real recording', { x: 600, y: y + 170, size: 44, color: C.muted, at: lay(s, 0.3), dur: FIRST });
    emph((o) => card(s, '', o), { x: 1320, y, w: 600, h: 480, overlap: true }, { stroke: C.accent, fill: C.card_bg }, lay(s, 0.4), at(s, 0.35));
    emph((o) => s.icon('workflow', o), { x: 1320, y: y - 90, size: 180, color: C.muted }, { color: C.accent }, lay(s, 0.5), at(s, 0.35));
    s.text('EXPLAIN', { x: 1320, y: y + 90, size: 72, font: F.title, color: C.title, at: lay(s, 0.7), dur: FIRST });
    tx(s, 'animated diagram', { x: 1320, y: y + 170, size: 44, color: C.muted, at: lay(s, 1), dur: FIRST });
  },
  x07(s) {
    s.camera([]);
    title(s, 'Kokoro on this laptop', { y: 220 });
    hbars(s, [
      { label: 'speech', value: 7.9, valueText: '7.9 s', color: C.accent2 },
      { label: 'generated in', value: 1.8, valueText: '1.8 s', color: C.accent },
    ], 7.9);
    tx(s, 'more than *4×* faster than real time', { y: s.cy + 270, size: 48, color: C.body, at: at(s, 0.45), dur: IN });
  },
  // memoria de Kokoro medida (METRICS.values.tts_vram_gb); sin METRICS, 0.9.
  x08(s) {
    const v = metric('values.tts_vram_gb', 0.9);
    memBar(s, { value: v, valueText: metric('display.tts_vram', `${v} GB`), head: 'Kokoro: *GPU memory*', color: C.accent2 });
  },

  // 0:45 re-hook: twelve -> 12
  x09(s) {
    s.camera([]);
    tx(s, 'we wrote', { x: 560, y: s.cy - 130, size: 40, color: C.muted, at: -1 });
    s.text('twelve', { x: 560, y: s.cy, size: 120, font: F.mono, color: C.title, at: -1 });
    arrow(s, [820, s.cy], [1100, s.cy], { at: lay(s, 0.3), dur: FIRST });
    tx(s, 'Whisper wrote', { x: 1320, y: s.cy - 130, size: 40, color: C.muted, at: lay(s, 0.6), dur: FIRST });
    // "12" está desde el inicio en gris; se vuelve rojo y se marca con la narración ("in digits")
    emph((o) => s.text('12', o), { id: 'n', x: 1320, y: s.cy, size: 120, font: F.mono, color: C.muted }, { color: C.negative }, lay(s, 1), at(s, 0.35));
    s.annotate('n_on', { type: 'circle', color: C.negative, at: at(s, 0.55), dur: IN });
  },
  x10(s) {
    s.camera([]);
    const a = ['We', 'built', 'a', 'video', 'in', 'twelve', 'minutes'];
    const b = ['We', 'built', 'a', 'video', 'in', '12', 'minutes'];
    const xs = s.row(7, { width: 1500 });
    const T2 = at(s, 0.4);   // la pareja que no coincide se pone roja
    tx(s, 'script', { y: s.cy - 220, size: 40, color: C.muted, at: -1 });
    tx(s, 'Whisper', { y: s.cy + 220, size: 40, color: C.muted, at: -1 });
    a.forEach((w, i) => {
      const bad = i === 5, f1 = i ? lay(s, i / 9) : -1, f2 = lay(s, (i + 2) / 9);
      const top = { x: xs[i], y: s.cy - 120, size: 52, font: F.mono, color: C.title };
      const bot = { x: xs[i], y: s.cy + 120, size: 52, font: F.mono, color: C.title };
      if (bad) {
        emph((o) => s.text(w, o), top, { color: C.negative }, f1, T2);
        emph((o) => s.text(b[i], o), bot, { color: C.negative }, f2, T2);
      } else {
        s.text(w, { ...top, at: f1, dur: FIRST });
        s.text(b[i], { ...bot, at: f2, dur: FIRST });
      }
      s.line([[xs[i], s.cy - 75], [xs[i], s.cy + 75]], { color: C.muted, dashed: bad, at: f2, dur: FIRST });
      if (bad) s.line([[xs[i], s.cy - 75], [xs[i], s.cy + 75]], { color: C.negative, dashed: true, width: 6, at: T2, dur: IN });
    });
  },
  x11(s) {
    s.camera([]);
    const words = [['We', 0, 0.48], ['built', 0.48, 0.7], ['a', 0.7, 0.84], ['video', 0.84, 1.16],
      ['in', 1.16, 1.44], ['12', 1.44, 1.74], ['minutes', 1.74, 2.06]];
    // título + tarjeta blanca con la línea de tiempo: el cuadro no queda como una franja fina
    const x0 = 210, W = 1500, sc = W / 2.06, y = 560, H = 180;
    title(s, 'Word *timestamps*', { y: 250 });
    s.draw({ at: -1 }, (ctx) => {
      ctx.fillStyle = C.card_bg; ctx.strokeStyle = C.card_border; ctx.lineWidth = T.card.border;
      ctx.beginPath(); ctx.roundRect(x0 - 60, 390, W + 120, 380, T.card.radius); ctx.fill(); ctx.stroke();
    });
    words.forEach(([w, a, b], i) => {
      const x = x0 + a * sc, w2 = (b - a) * sc, f = i ? lay(s, i / 6) : -1;
      s.draw({ at: f, enter: 'fade', dur: FIRST, box: { x: x + w2 / 2, y, w: w2 - 8, h: H } }, (ctx) => {
        ctx.fillStyle = i % 2 ? C.accent2_tint : C.accent_tint;
        ctx.strokeStyle = i % 2 ? C.accent2 : C.accent; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.roundRect(x + 4, y - H / 2, w2 - 8, H, T.card.radius); ctx.fill(); ctx.stroke();
      });
      s.text(w, { x: x + w2 / 2, y, size: 56, color: C.title, at: f, dur: FIRST });
    });
    [0, 1, 2].forEach((t) => s.text(`${t} s`, { x: x0 + t * sc, y: y + H / 2 + 50, size: 36, font: F.mono, color: C.muted, at: -1 }));
    // cabezal de lectura que recorre las palabras con la narración
    s.draw({ at: -1 }, (ctx) => {
      const hx = x0 + s.clamp(s.t / (s.dur * 0.85), 0, 1) * W;
      ctx.fillStyle = C.title; ctx.fillRect(hx - 2, y - H / 2 - 30, 4, H + 60);
    });
  },
  x12(s) {
    s.camera([]);
    s.text('twelve', { y: s.cy - 90, size: 150, font: F.mono, bold: true, color: C.title, at: -1 });
    // eje con marcas de inicio y fin bajo la palabra; las cifras llegan con la narración
    s.draw({ at: lay(s, 0.2), enter: 'fade', dur: FIRST, box: { x: s.cx, y: s.cy + 10, w: 600, h: 60 } }, (ctx) => {
      ctx.strokeStyle = C.muted; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.moveTo(s.cx - 300, s.cy + 10); ctx.lineTo(s.cx + 300, s.cy + 10); ctx.stroke();
      ctx.strokeStyle = C.accent; ctx.lineWidth = 6;
      for (const x of [s.cx - 280, s.cx + 280]) { ctx.beginPath(); ctx.moveTo(x, s.cy - 18); ctx.lineTo(x, s.cy + 38); ctx.stroke(); }
    });
    s.text('1.44 s → 1.74 s', { y: s.cy + 110, size: 80, font: F.mono, color: C.accent, at: at(s, 0.25), dur: IN });
  },

  // 1:07 how the picture is built
  x13(s) {
    s.camera([]);
    s.icon('cpu', { x: 640, y: s.cy - 40, size: 220, bg: 'circle', color: C.accent, label: 'processor', labelSize: 48, labelColor: C.body, at: -1 });
    s.icon('monitor', { x: 1280, y: s.cy - 40, size: 220, bg: 'circle', color: C.muted, opacity: 0.35, label: 'graphics card', labelSize: 48, labelColor: C.body, at: lay(s, 0.2), dur: FIRST });
    tx(s, 'no GPU needed', { y: s.cy + 260, size: 60, bold: true, color: C.positive, at: at(s, 0.45), dur: IN });
  },
  x14(s) {
    s.camera([]);
    s.draw({ x: 560, y: s.cy, at: -1, box: { x: 0, y: 0, w: 220, h: 220, round: true } }, (ctx) => {
      const r = 80 + 10 * Math.sin(s.t * 5);
      ctx.fillStyle = C.negative; ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();
    });
    s.text('REC', { x: 560, y: s.cy + 170, size: 56, font: F.mono, bold: true, color: C.negative, at: -1 });
    emph((o) => card(s, 'real demo', o), { id: 'd', x: 1340, y: s.cy, icon: 'monitor-play', size: 64 }, HOT, lay(s, 0.4), at(s, 0.35));
    arrow(s, [720, s.cy], 'd', { at: lay(s, 1), dur: FIRST });
  },
  x15(s) {
    s.camera([]);
    s.icon('timer', { x: s.cx, y: s.cy - 160, size: 200, color: C.accent, at: -1 });
    title(s, 'a new picture every *3–5 s*', { y: s.cy + 70, size: 80 });
    const xs = s.row(5, { width: 900 });
    xs.forEach((x, i) => s.draw({ at: -1, box: { x, y: s.cy + 230, w: 140, h: 80 } }, (ctx) => {
      const on = Math.floor(s.t / Math.max(0.4, s.dur / 6)) % 5 === i;
      ctx.fillStyle = on ? C.accent : C.track;
      ctx.beginPath(); ctx.roundRect(x - 70, s.cy + 190, 140, 80, T.card.radius); ctx.fill();
    }));
  },
  x16(s) {
    s.camera([]);
    const x0 = 260, W = 1400;
    const speaking = (u) => (u > 0.08 && u < 0.38) || (u > 0.55 && u < 0.9);
    s.text('voice', { x: x0 - 40, y: s.cy - 120, size: 44, align: 'right', color: C.accent, at: -1 });
    s.text('music', { x: x0 - 40, y: s.cy + 140, size: 44, align: 'right', color: C.accent2, at: -1 });
    // ambas ondas completas desde el frame 0, tenues; un cabezal las recorre y enciende lo ya sonado
    // at: 0 sin entrada = visible en el frame 0 (check pide al menos un elemento que "entre")
    s.draw({ at: 0, box: { x: x0 + W / 2, y: s.cy, w: W, h: 420 } }, (ctx) => {
      const head = s.clamp(s.t / (s.dur * 0.85), 0, 1);
      for (let i = 0; i < 140; i++) {
        const u = i / 139;
        const x = x0 + u * W;
        const v = speaking(u) ? 50 + 40 * Math.abs(Math.sin(i * 1.7)) : 4;
        const m = (speaking(u) ? 14 : 55) * (0.7 + 0.3 * Math.abs(Math.sin(i * 0.9)));
        ctx.globalAlpha = u <= head ? 1 : 0.4;
        ctx.fillStyle = C.accent; ctx.fillRect(x, s.cy - 120 - v, 6, v * 2);
        ctx.fillStyle = C.accent2; ctx.fillRect(x, s.cy + 140 - m, 6, m * 2);
      }
      ctx.globalAlpha = 1;
      ctx.fillStyle = C.title; ctx.fillRect(x0 + head * W - 2, s.cy - 220, 4, 440);
    });
  },
  x17(s) {
    s.camera([]);
    const items = [['film', 'clips'], ['mic', 'voice'], ['music', 'music'], ['captions', 'subtitles']];
    // cuatro filas de 150 px centradas en s.cy - 60: la última etiqueta queda sobre la banda de subtítulos
    const ys = [0, 1, 2, 3].map((i) => s.cy - 60 + (i - 1.5) * 150);
    items.forEach(([ic, l], i) => {
      s.icon(ic, { id: `i${i}`, x: 380, y: ys[i], size: 80, color: C.accent2, label: l, labelSize: 34, labelColor: C.body, at: i ? lay(s, i * 0.15) : -1, dur: FIRST });
    });
    emph((o) => card(s, 'FFmpeg', o), { id: 'f', x: 1000, y: s.cy - 40, size: 64 }, HOT, lay(s, 0.5), at(s, 0.3));
    items.forEach((_, i) => arrow(s, `i${i}`, 'f', { at: lay(s, 0.6 + i * 0.05), dur: FIRST }));
    card(s, 'final.mp4', { id: 'o', x: 1560, y: s.cy - 40, icon: 'file-video', size: 52, at: lay(s, 0.8), dur: FIRST });
    arrow(s, 'f', 'o', { at: lay(s, 1), dur: FIRST });
    s.annotate('o', { type: 'box', color: C.accent, at: at(s, 0.6), dur: IN });
  },
  x18(s) {
    s.camera([]);
    s.text('1920 × 1080', { y: s.cy - 70, size: 150, font: F.mono, bold: true, color: C.kpi, at: -1 });
    tx(s, '*30* frames per second', { y: s.cy + 110, size: 64, color: C.muted, at: lay(s, 0.5), dur: FIRST });
  },

  // 1:43 where the files live
  x19(s) {
    s.camera([]);
    s.icon('folder', { x: 560, y: s.cy - 160, size: 170, color: C.muted, label: 'temp (local)', labelSize: 44, labelColor: C.body, at: -1 });
    const g = s.grid(4, 2, { x: 560, y: s.cy + 150, w: 460, h: 200, gap: 20 });
    g.forEach((c, i) => s.icon('file', { x: c.x, y: c.y, size: 60, color: C.muted, at: lay(s, i * 0.06), dur: FIRST }));
    s.icon('cloud', { x: 1360, y: s.cy - 160, size: 170, color: C.accent2, label: 'runs (synced)', labelSize: 44, labelColor: C.body, at: lay(s, 0.5), dur: FIRST });
    arrow(s, [830, s.cy - 160], [1180, s.cy - 160], { at: lay(s, 0.7), dur: FIRST });
    // los dos resultados están desde el inicio en gris; se encienden cuando "se mueven"
    emph((o) => s.text('final.mp4', o), { x: 1360, y: s.cy + 110, size: 44, font: F.mono, color: C.muted }, { color: C.accent }, lay(s, 0.8), at(s, 0.5));
    emph((o) => s.text('manifest.json', o), { x: 1360, y: s.cy + 180, size: 44, font: F.mono, color: C.muted }, { color: C.accent }, lay(s, 1), at(s, 0.55));
  },
  x20(s) {
    s.camera([]);
    card(s, 'tmp/final.mp4', { id: 'a', x: 480, y: s.cy - 30, font: F.mono, size: 48, at: -1 });
    emph((o) => card(s, 'runs/final.mp4', o), { id: 'b', x: 1440, y: s.cy - 30, font: F.mono, size: 48 }, HOT, lay(s, 0.4), at(s, 0.35));
    arrow(s, 'a', 'b', { label: 'rename', labelFont: F.body, at: lay(s, 1), dur: FIRST });
    emph((o) => s.text('all or nothing', o), { y: s.cy + 170, size: 72, font: F.title, color: C.muted }, { color: C.accent }, lay(s, 1), at(s, 0.5));
  },

  // 1:56 re-hook: the failure. Terminal oscura (tema oscuro) con la lista de rutas vieja: el
  // comando se escribe a 35 ms/carácter con cursor; falta la de FFmpeg y llega en rojo con la voz.
  x21(s) {
    s.camera([]);
    const size = Z.mono, w = 1000, y = 470;
    const cmd = '$env:Path -split ";"';
    const t1 = cmd.length / M.command_cps;            // fin del comando (tick)
    const paths = ['C:\\Windows\\system32', 'C:\\Program Files\\nodejs', '...\\Git\\cmd', '...\\anaconda3\\Scripts'];
    const miss = Math.max(t1 + 0.6, at(s, 0.45));
    s.terminal([
      { cmd, at: 0 },
      ...paths.map((l, i) => ({ out: l, at: t1 + 0.08 + i * 0.06 })),
      { out: '...\\ffmpeg\\bin   missing', at: miss, color: C.term_fail },
    ], { y, w, size, rows: 6, prompt: '>', cps: M.command_cps, title: 'PowerShell', at: 0, enter: 'none' });
    cue(s, T.sfx.rules.typewriter_end, t1);
    // geometría de s.terminal (engine/stage.js): fila n de texto arriba en top + n·1,55·size
    const lh = size * 1.55, h = 6 * lh + size * 1.5 + size * 0.9 * 1.6;
    const top = y - h / 2 + size * 1.5 + size * 0.9 * 0.8, left = s.cx - w / 2 + size * 0.9;
    const rowY = top + 5 * lh + size * 0.55;
    // hueco punteado donde debería estar la ruta de FFmpeg, hasta que la voz la nombra
    s.draw({ at: t1 + 0.35, out: miss, exit: 'none', enter: 'fade', dur: FIRST }, (ctx) => {
      ctx.setLineDash([10, 10]); ctx.strokeStyle = C.term_muted; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.roundRect(left - 10, rowY - lh / 2, 640, lh, T.card.radius); ctx.stroke(); ctx.setLineDash([]);
    });
    s.annotate({ x: left + 310, y: rowY, w: 640, h: lh }, { type: 'box', color: C.negative, at: Math.max(miss + 0.2, at(s, 0.6)), dur: IN });
    tx(s, 'its path list was *stale*', { y: 790, size: 52, color: C.body, at: at(s, 0.7), dur: IN });
  },
  x22(s) {
    s.camera([]);
    const y = s.cy + 40;
    arrow(s, [250, y], [1680, y], { at: -1 });
    s.circle({ x: 560, y, r: 22, fill: C.accent2, color: C.accent2, overlap: true, at: 0, dur: FIRST });
    tx(s, 'terminal opened', { x: 560, y: y + 90, size: 44, at: 0, dur: FIRST });
    s.icon('terminal', { x: 560, y: y - 150, size: 110, color: C.accent2, at: lay(s, 0.2), dur: FIRST });
    // el segundo evento está desde el inicio, apagado; se enciende con la narración
    emph((o) => s.circle(o), { x: 1260, y, r: 22, fill: C.muted, color: C.muted, overlap: true }, { fill: C.accent, color: C.accent }, lay(s, 0.6), at(s, 0.35));
    tx(s, 'FFmpeg installed', { x: 1260, y: y + 90, size: 44, at: lay(s, 0.8), dur: FIRST });
    s.icon('eye-off', { x: 1260, y: y - 150, size: 110, color: C.negative, at: at(s, 0.55), dur: IN });
  },
  // tarjeta de regla: "3 failures → stop and report"
  x23(s) {
    s.camera([]);
    const y = s.cy + 60;
    s.icon('octagon-x', { x: s.cx, y: s.cy - 170, size: 150, color: C.warning, at: -1 });
    card(s, '', { x: s.cx, y, w: 1560, h: 240, overlap: true, at: 0 });
    tx(s, '*3* failures', { x: s.cx - 320, y, size: 76, font: F.title, color: C.title, mark: C.warning, at: 0.05, dur: FIRST });
    arrow(s, [s.cx - 90, y], [s.cx + 60, y], { at: lay(s, 0.5), dur: FIRST });
    emph((o) => s.text('stop and report', o), { x: s.cx + 420, y, size: 76, font: F.title, color: C.muted }, { color: C.accent }, lay(s, 1), at(s, 0.3));
  },

  // 2:30 verdict: cifras medidas (METRICS.display); sin METRICS, las llaves del guion. Tarjetas de
  // marcador: la de electricidad entra (rise + swoosh) y su cifra cuenta cuando la voz llega a ella.
  x24(s) {
    s.camera([]);
    const b = data('x24').braces;
    const software = metric('display.software', b[0] || '$0');
    const electricity = metric('display.electricity', b[1] || '?');
    // ×K: tarjetas 600×320 -> 780×416, separadas 60 px y dentro del área segura
    const y = s.cy, f2 = lay(s, 0.5), w = 600 * K, h = 320 * K, dx = w / 2 + 30;
    const [xa, xb] = [s.cx - dx, s.cx + dx];
    card(s, '', { x: xa, y, w, h, overlap: true, at: -1 });
    tx(s, 'Software', { x: xa, y: y - 85 * K, size: Z.body * K, color: C.muted, at: -1 });
    counter(s, software, { x: xa, y: y + 40 * K, size: 110 * K, color: C.cost, at: -1 });
    emph((o) => card(s, '', o), { x: xb, y, w, h, overlap: true }, { stroke: C.cost, fill: C.card_bg }, f2, at(s, 0.35));
    tx(s, 'Electricity', { x: xb, y: y - 85 * K, size: Z.body * K, color: C.muted, at: f2, dur: FIRST });
    counter(s, `≈ ${electricity}`, { x: xb, y: y + 40 * K, size: 110 * K, color: C.cost, at: f2 });
  },
  x25(s) {
    s.camera([]);
    const wall = metric('display.wall', data('x25').braces[0] || '?');
    s.icon('timer', { x: s.cx, y: s.cy - 190, size: 170, color: C.accent, at: -1 });
    // cuenta los segundos medidos (METRICS.wall_s) con el formato de la cifra; al final, la cifra tal cual
    counter(s, wall, { y: s.cy + 30, size: 150, color: C.kpi, at: -1, value: metric('wall_s', NaN),
      format: (v) => { const r = Math.round(v); return `${Math.floor(r / 60)} min ${r % 60} s`; } });
    tx(s, 'script → *MP4*, on this laptop', { y: s.cy + 200, size: 52, color: C.muted, at: lay(s, 1), dur: FIRST });
  },
  x26(s) {
    const v = metric('values.vram_peak_gb', num(data('x26').braces[0], 2.3));
    memBar(s, { value: v, valueText: metric('display.vram_peak', `${v} GB`), head: 'Peak *GPU memory*' });
  },
  // límites como lista "sin X": lo que aún no hay, tachado en accent cuando la voz lo dice
  x27(s) {
    s.camera([]);
    title(s, '*Limits*', { x: 560, y: 250, align: 'left' });
    const items = ['real screen footage', 'a custom voice', 'a thumbnail'];
    const strikes = [at(s, 0.3), at(s, 0.6), at(s, 0.75)];
    items.forEach((t, i) => {
      const y = 405 + i * 115, t0 = lay(s, i / 2);
      s.icon('circle-alert', { x: 586, y, size: 48, color: C.warning, at: -1 });
      tx(s, t, { id: `l${i}`, x: 636, y, size: 60, color: C.title, align: 'left', at: i ? t0 : -1, dur: FIRST });
      s.annotate(`l${i}`, { type: 'strike', color: C.accent, width: 6, at: strikes[i], dur: M.strike });
    });
  },

  // escena 24 (id fijo xcc): callout grande en pantalla + ícono CC = transcripción completa como subtítulos
  xcc(s) {
    s.camera([]);
    // el callout de ejemplo, con el look del callout real (Inter, una palabra en accent), más grande
    tx(s, 'one word in *blue*', { y: s.cy - 150, size: 120, font: F.body, bold: true, color: C.title, at: -1 });
    // ícono CC: tarjeta con borde grueso en tinta, entra subiendo con swoosh
    const cy = s.cy + 120, w = 260, h = 170, t0 = lay(s, 0.5);
    cue(s, T.sfx.rules.card_enter, t0);
    s.draw({ at: t0, enter: M.card_enter, dur: FIRST, box: { x: s.cx, y: cy, w, h } }, (ctx) => {
      ctx.fillStyle = C.card_bg; ctx.strokeStyle = C.title; ctx.lineWidth = 10;
      ctx.beginPath(); ctx.roundRect(s.cx - w / 2, cy - h / 2, w, h, 28); ctx.fill(); ctx.stroke();
    });
    s.text('CC', { x: s.cx, y: cy, size: 96, font: F.title, bold: true, color: C.title, at: t0, enter: M.card_enter, dur: FIRST });
    tx(s, 'full transcript as *closed captions*', { y: cy + 150, size: 44, color: C.muted, at: lay(s, 1), dur: FIRST });
  },

  // 2:50 next
  x28(s) {
    s.camera([]);
    s.icon('pen-line', { x: s.cx, y: s.cy - 190, size: 150, color: C.accent, at: -1 });
    title(s, 'Next: the *Writer* agent', { y: s.cy + 20 });
    tx(s, 'The Build Log', { y: s.cy + 150, size: 56, color: C.muted, at: lay(s, 1), dur: FIRST });
  },
});

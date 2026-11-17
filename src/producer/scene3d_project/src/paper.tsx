// Piezas comunes del tema "paper" para escenas 3D (Three.js vía @remotion/three).
// REGLA: aquí no hay ningún color, fuente ni tiempo escrito a mano. Todo llega en las props desde
// src/producer/theme_paper.py (scenes_theme) a través de src/producer/scene3d.py.
import React, {useEffect, useMemo, useState} from 'react';
import {
  AbsoluteFill,
  Html5Audio,
  Sequence,
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {RoundedBoxGeometry} from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';

// ------------------------------------------------------------------ tipos (lo que inyecta scene3d.py)

export type Theme = {
  name: string;
  version: number;
  c: Record<string, string> & {glow_alpha: number; glow_radius: number};
  family: {heading: string; body: string; mono: string};
  size: {title: number; subtitle: number; body: number; mono: number; small: number; figure_scale: number};
  weight: {title: number; body: number; mono: number};
  grid: {px: number; width: number};
  card: {radius: number; border: number; shadow: {x: number; y: number; blur: number; color: string}};
  motion: {enter: number; enter_min: number; enter_max: number; title_cps: number; counter: number; strike: number};
  sfx: {files: Record<string, string>; volume: number; rules: Record<string, string>};
  frame: {subtitle_top: number};
};

export type FontAsset = {family: string; weight: number; src: string};

export type Layout = {
  aspect: '16:9' | '9:16';
  width: number;
  height: number;
  fps: number;
  frames: number;
  // franjas horizontales reservadas [y0, y1] en px (subtítulos, karaoke de Shorts, UI de Shorts)
  reserved: [number, number][];
};

export type SceneProps = {
  theme: Theme | null;
  fonts: FontAsset[];
  metrics: Record<string, any> | null;
  data: Record<string, any>;
  layout: Layout;
  scene3d: {gl_probe: boolean; supersample: number};
};

export const requireTheme = (theme: Theme | null): Theme => {
  if (!theme) {
    throw new Error('THEME missing: render through producer.scene3d (it injects --props with theme_paper)');
  }
  return theme;
};

// ------------------------------------------------------------------ tiempo y movimiento

export const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
// ease-out cúbico: la regla del canal es ease-out de 250–400 ms en toda entrada
export const easeOut = (x: number) => 1 - Math.pow(1 - clamp(x), 3);
// fracción de una entrada que empieza en t0 y dura THEME.motion.enter
export const enter = (t: number, t0: number, theme: Theme, dur = theme.motion.enter) =>
  easeOut((t - t0) / dur);
// lay(dur, f): inicio de un elemento estructural; con duración ≤ enter termina antes de min(0,6 s, 0,25·dur)
export const lay = (theme: Theme, dur: number, f: number) =>
  Math.max(0, Math.min(0.6, 0.25 * dur) - theme.motion.enter) * f;

export const useClock = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  return {frame, fps, t: frame / fps, dur: durationInFrames / fps, W: width, H: height};
};

// ------------------------------------------------------------------ METRICS

export const metric = <T,>(metrics: Record<string, any> | null, path: string, fallback: T): T => {
  let v: any = metrics;
  for (const k of path.split('.')) {
    if (v === null || v === undefined || typeof v !== 'object') return fallback;
    v = v[k];
  }
  if (typeof fallback === 'number') return (Number.isFinite(v) ? v : fallback) as T;
  return (v === null || v === undefined || v === '' ? fallback : String(v)) as T;
};

// ------------------------------------------------------------------ colores

const hexRgb = (hex: string) => {
  const h = hex.replace('#', '');
  const f = h.length === 3 ? h.split('').map((x) => x + x).join('') : h;
  return [0, 2, 4].map((i) => parseInt(f.slice(i, i + 2), 16));
};
export const rgba = (hex: string, a: number) => `rgba(${hexRgb(hex).join(',')},${a})`;
export const mix = (a: string, b: string, k: number) => {
  const A = new THREE.Color(a);
  return '#' + A.lerp(new THREE.Color(b), clamp(k)).getHexString();
};

// ------------------------------------------------------------------ fuentes y efectos

// Carga las fuentes OFL del tema (assets/fonts, copiadas a public/ por scene3d.py) antes del primer frame.
export const PaperFonts: React.FC<{fonts: FontAsset[]; children: React.ReactNode}> = ({fonts, children}) => {
  const [handle] = useState(() => delayRender('Loading paper fonts'));
  useEffect(() => {
    Promise.all(
      fonts.map((f) =>
        new FontFace(f.family, `url(${staticFile(f.src)})`, {weight: String(f.weight)})
          .load()
          .then((ff) => document.fonts.add(ff)),
      ),
    )
      .then(() => continueRender(handle))
      .catch((e) => cancelRender(e));
  }, [fonts, handle]);
  return <>{children}</>;
};

// Efecto de sonido del tema (THEME.sfx: tick al terminar un typewriter, swoosh al entrar una tarjeta,
// pop al terminar un contador). Los archivos ya están a −18 dB respecto a la voz.
export const Sfx: React.FC<{theme: Theme; name: string; at: number}> = ({theme, name, at}) => {
  const {fps, durationInFrames} = useVideoConfig();
  const src = theme.sfx.files[name];
  const from = Math.round(at * fps);
  if (!src || from >= durationInFrames - 1) return null;
  return (
    <Sequence from={from} layout="none">
      <Html5Audio src={staticFile(src)} volume={theme.sfx.volume} />
    </Sequence>
  );
};

// ------------------------------------------------------------------ texto (capa HTML sobre el canvas)

type Seg = {text: string; key: boolean};
// "Peak *GPU memory*" -> segmentos; la palabra clave (entre asteriscos) va en accent
export const parseKeywords = (s: string): Seg[] =>
  s.split(/(\*[^*]+\*)/).filter(Boolean).map((p) =>
    p.startsWith('*') && p.endsWith('*') ? {text: p.slice(1, -1), key: true} : {text: p, key: false},
  );
export const plain = (s: string) => s.replace(/\*/g, '');

// Título con máquina de escribir desde t = 0 (THEME.motion.title_cps). Las letras aún no escritas
// ocupan su sitio (opacity 0), así el centrado no salta. En el frame 0 ya hay una letra.
export const Title: React.FC<{theme: Theme; text: string; t: number; y: number; size?: number; maxWidth?: number}> = ({
  theme, text, t, y, size, maxWidth,
}) => {
  const c = theme.c;
  const shown = Math.floor(t * theme.motion.title_cps) + 1;
  let i = 0;
  return (
    <div
      style={{
        position: 'absolute', left: 0, right: 0, top: y, transform: 'translateY(-50%)', textAlign: 'center',
        fontFamily: `'${theme.family.heading}'`, fontWeight: theme.weight.title, fontSize: size ?? theme.size.title,
        lineHeight: 1.08, color: c.title, letterSpacing: '-0.01em', margin: '0 auto', maxWidth,
      }}
    >
      {parseKeywords(text).map((seg, si) => (
        <span key={si} style={{color: seg.key ? c.keyword : c.title}}>
          {seg.text.split('').map((ch, ci) => {
            const visible = i++ < shown;
            return <span key={ci} style={{opacity: visible ? 1 : 0}}>{ch}</span>;
          })}
        </span>
      ))}
    </div>
  );
};
export const titleEnd = (theme: Theme, text: string) => plain(text).length / theme.motion.title_cps;

// Contador: "2.3 GB" -> anima la cifra de 0 al valor (THEME.motion.counter, ease-out), conservando decimales
export const counterText = (display: string, p: number) => {
  const m = display.match(/^(.*?)(\d+(?:\.\d+)?)(.*)$/);
  if (!m) return display;
  const dec = (m[2].split('.')[1] || '').length;
  return `${m[1]}${(parseFloat(m[2]) * clamp(p)).toFixed(dec)}${m[3]}`;
};

export const Label: React.FC<{
  theme: Theme; x: number; y: number; text: string; color?: string; font?: 'body' | 'mono' | 'heading';
  size?: number; weight?: number; opacity?: number; align?: 'center' | 'left' | 'right';
}> = ({theme, x, y, text, color, font = 'body', size, weight, opacity = 1, align = 'center'}) => {
  const fam = theme.family[font];
  const tx = align === 'center' ? '-50%' : align === 'right' ? '-100%' : '0';
  return (
    <div
      style={{
        position: 'absolute', left: x, top: y, transform: `translate(${tx}, -50%)`, whiteSpace: 'nowrap',
        fontFamily: `'${fam}'`, fontSize: size ?? (font === 'mono' ? theme.size.mono : theme.size.body),
        fontWeight: weight ?? (font === 'mono' ? theme.weight.mono : 600), color: color ?? theme.c.body, opacity,
      }}
    >
      {text}
    </div>
  );
};

// Brillo radial arriba a la derecha (THEME.c.glow al THEME.c.glow_alpha, radio THEME.c.glow_radius a 1080p)
export const Glow: React.FC<{theme: Theme}> = ({theme}) => {
  const {width, height} = useVideoConfig();
  const r = theme.c.glow_radius * (Math.max(width, height) / 1920);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background: `radial-gradient(circle ${r}px at 100% 0%, ${rgba(theme.c.glow, theme.c.glow_alpha)} 0%, ${rgba(
          theme.c.glow, 0)} 100%)`,
      }}
    />
  );
};

// ------------------------------------------------------------------ cámara

export type CamSpec = {
  fov: number; position: [number, number, number]; target: [number, number, number];
  W: number; H: number; cx: number; cy: number; // el objetivo aparece en (cx, cy) del cuadro
};

// Órbita: azimut y elevación en grados alrededor de target
export const orbit = (o: {
  target: [number, number, number]; radius: number; elevation: number; azimuth: number; fov: number;
  W: number; H: number; cx: number; cy: number;
}): CamSpec => {
  const el = THREE.MathUtils.degToRad(o.elevation), az = THREE.MathUtils.degToRad(o.azimuth);
  const [tx, ty, tz] = o.target;
  return {
    fov: o.fov, target: o.target, W: o.W, H: o.H, cx: o.cx, cy: o.cy,
    position: [tx + o.radius * Math.cos(el) * Math.sin(az), ty + o.radius * Math.sin(el), tz + o.radius * Math.cos(el) * Math.cos(az)],
  };
};

export const applyCamera = (cam: THREE.PerspectiveCamera, s: CamSpec) => {
  cam.fov = s.fov;
  cam.aspect = s.W / s.H;
  cam.near = 0.1;
  cam.far = 400;
  cam.position.set(...s.position);
  cam.up.set(0, 1, 0);
  cam.lookAt(...s.target);
  // desplaza el centro óptico para que el objetivo quede en (cx, cy)
  cam.setViewOffset(s.W, s.H, s.W / 2 - s.cx, s.H / 2 - s.cy, s.W, s.H);
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
};

// Cámara de proyección (fuera del canvas) para anclar etiquetas HTML a puntos 3D
export const useProjector = (spec: CamSpec) => {
  const cam = useMemo(() => new THREE.PerspectiveCamera(), []);
  applyCamera(cam, spec);
  return (p: [number, number, number]) => {
    const v = new THREE.Vector3(...p).project(cam);
    return {x: ((v.x + 1) / 2) * spec.W, y: ((1 - v.y) / 2) * spec.H};
  };
};

// Dentro del canvas: copia la cámara del frame actual (se ejecuta en el render, antes de advance())
export const CameraRig: React.FC<{spec: CamSpec}> = ({spec}) => {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  applyCamera(camera, spec);
  return null;
};

// px por unidad 3D a la distancia del objetivo (para que la cuadrícula mida THEME.grid.px)
export const pxPerUnit = (s: CamSpec) => {
  const d = new THREE.Vector3(...s.position).distanceTo(new THREE.Vector3(...s.target));
  return s.H / (2 * d * Math.tan(THREE.MathUtils.degToRad(s.fov) / 2));
};

// ------------------------------------------------------------------ escenario: papel, cuadrícula, luces, sombras

const FLOOR = 240; // lado del plano del suelo (unidades)
const CELLS_PER_TEX = 4;

// Suelo de papel: bg + cuadrícula de THEME.grid.px (medida a la distancia del objetivo), sin iluminación
// (MeshBasic: el color es exactamente bg); niebla en bg para que el fondo se funda sin horizonte;
// un plano ShadowMaterial encima recibe la sombra suave (VSM) en textTitle a baja opacidad.
export const PaperStage: React.FC<{theme: Theme; cell: number; fogNear: number; fogFar: number; shadowOpacity?: number}> = ({
  theme, cell, fogNear, fogFar, shadowOpacity = 0.13,
}) => {
  const c = theme.c;
  const gl = useThree((s) => s.gl);
  const tex = useMemo(() => {
    const N = 512, step = N / CELLS_PER_TEX;
    const cv = document.createElement('canvas');
    cv.width = cv.height = N;
    const g = cv.getContext('2d')!;
    g.fillStyle = c.bg;
    g.fillRect(0, 0, N, N);
    g.fillStyle = c.grid;
    const lw = Math.max(2, Math.round(theme.grid.width * step / theme.grid.px * 1.5));
    for (let k = 0; k < CELLS_PER_TEX; k++) {
      g.fillRect(k * step, 0, lw, N);
      g.fillRect(0, k * step, N, lw);
    }
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = gl.capabilities.getMaxAnisotropy();
    const rep = FLOOR / (cell * CELLS_PER_TEX);
    t.repeat.set(rep, rep);
    return t;
  }, [c.bg, c.grid, theme.grid, cell, gl]);
  return (
    <>
      <color attach="background" args={[c.bg]} />
      <fog attach="fog" args={[c.bg, fogNear, fogFar]} />
      <mesh rotation-x={-Math.PI / 2}>
        <planeGeometry args={[FLOOR, FLOOR]} />
        <meshBasicMaterial map={tex} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.003} receiveShadow>
        <planeGeometry args={[FLOOR, FLOOR]} />
        <shadowMaterial color={c.title} opacity={shadowOpacity} transparent />
      </mesh>
    </>
  );
};

// Luz: cielo blanco (card_bg) sobre suelo bg + una direccional suave con sombra VSM (difuminada)
export const PaperLights: React.FC<{theme: Theme; span: number; target?: [number, number, number]}> = ({
  theme, span, target = [0, 0, 0],
}) => {
  const c = theme.c;
  const light = useMemo(() => new THREE.DirectionalLight(), []);
  const [tx, ty, tz] = target;
  light.color.set(c.card_bg);
  light.intensity = 1.55;
  light.position.set(tx - span * 0.35, ty + span * 1.1, tz + span * 0.55);
  light.target.position.set(tx, ty, tz);
  light.castShadow = true;
  light.shadow.mapSize.set(2048, 2048);
  const sc = light.shadow.camera as THREE.OrthographicCamera;
  sc.left = -span; sc.right = span; sc.top = span; sc.bottom = -span; sc.near = 0.5; sc.far = span * 4;
  sc.updateProjectionMatrix();
  light.shadow.radius = 14;
  light.shadow.blurSamples = 24;
  light.shadow.bias = -0.0004;
  return (
    <>
      <hemisphereLight args={[c.card_bg, c.bg, 2.1]} />
      <primitive object={light} />
      <primitive object={light.target} />
    </>
  );
};

// Geometría de caja redondeada (cacheada por medidas)
const boxCache = new Map<string, THREE.BufferGeometry>();
export const roundedBox = (w: number, h: number, d: number, r: number, seg = 4) => {
  const k = [w, h, d, r, seg].join('|');
  if (!boxCache.has(k)) boxCache.set(k, new RoundedBoxGeometry(w, h, d, seg, r));
  return boxCache.get(k)!;
};

// Material mate del tema (MeshStandard, sin metal): mismo aspecto en todas las escenas 3D
export const Matte: React.FC<{color: string; opacity?: number}> = ({color, opacity = 1}) => (
  <meshStandardMaterial color={color} roughness={0.78} metalness={0} transparent={opacity < 1} opacity={opacity} />
);

// Diagnóstico: qué GPU/renderer usa Chrome (lo lee scene3d.py en el log, con --log=verbose)
export const glProbe = (state: {gl: THREE.WebGLRenderer}) => {
  const g = state.gl.getContext();
  const ext = g.getExtension('WEBGL_debug_renderer_info');
  const r = ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
  // eslint-disable-next-line no-console
  console.log(`[scene3d] GL_RENDERER=${r}`);
};

// Zonas libres según el formato: devuelve los y de título, sujeto 3D y lectura (cifras)
export const slots = (layout: Layout) => {
  const {height: H} = layout;
  if (layout.aspect === '9:16') {
    const band = layout.reserved[0] ?? [H * 0.42, H * 0.58];
    const ui = layout.reserved[1] ?? [H * 0.8, H];
    const titleY = H * 0.135;
    return {titleY, subjectY: (titleY + 90 + band[0]) / 2, readoutY: (band[1] + ui[0]) / 2 - 40, bottom: ui[0]};
  }
  const sub = layout.reserved[0]?.[0] ?? H * 0.8;
  return {titleY: H * 0.135, subjectY: H * 0.46, readoutY: sub - 100, bottom: sub};
};

// Distancia de cámara para que un objeto de `widthUnits` ocupe `frac` del ancho del cuadro
export const fitRadius = (widthUnits: number, frac: number, fov: number, W: number, H: number) =>
  widthUnits / (frac * 2 * Math.tan(THREE.MathUtils.degToRad(fov) / 2) * (W / H));

// Distancia cámara–objetivo (la niebla empieza más allá del sujeto)
export const camDist = (s: CamSpec) => new THREE.Vector3(...s.position).distanceTo(new THREE.Vector3(...s.target));

// Assembly3D: las cuatro entradas (clips, voz, música, subtítulos) como capas apiladas en el espacio;
// con la narración las capas bajan y se funden en un solo archivo (final.mp4, en accent).
// La profundidad es el argumento: el ensamblaje ES superponer capas. Equivalente 2D: x17 (flechas a FFmpeg).
import React from 'react';
import {AbsoluteFill} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {
  CameraRig, Glow, Label, Matte, PaperLights, PaperStage, SceneProps, Sfx, Theme, Title, camDist,
  enter, fitRadius, glProbe, lay, mix, orbit, pxPerUnit, requireTheme, roundedBox, slots, titleEnd, useClock,
  useProjector,
} from './paper';

const SLAB = {w: 7.2, h: 0.12, d: 2.1};
const GAP_OPEN = 0.95, GAP_SHUT = SLAB.h + 0.004;
const N_WAVE = 44;

// Patrón de cada capa sobre su cara superior (coordenadas locales: y = 0 es la cara superior)
const Pattern: React.FC<{kind: string; theme: Theme; fade: number}> = ({kind, theme, fade}) => {
  const c = theme.c;
  const col = mix(c.accent2, c.card_bg, fade);
  const x0 = -SLAB.w / 2 + 0.45, span = SLAB.w - 0.9;
  if (kind === 'clips') {
    return (
      <>
        {Array.from({length: 6}, (_, i) => (
          <mesh key={i} geometry={roundedBox(span / 6 - 0.12, 0.05, 1.35, 0.03, 2)}
            position={[x0 + (i + 0.5) * (span / 6), 0.025, 0]}>
            <Matte color={col} />
          </mesh>
        ))}
      </>
    );
  }
  if (kind === 'voice' || kind === 'music') {
    // onda determinista: voz con pausas (habla/silencio), música más suave y continua
    return (
      <>
        {Array.from({length: N_WAVE}, (_, i) => {
          const u = i / (N_WAVE - 1);
          const a = kind === 'voice'
            ? (u > 0.08 && u < 0.42) || (u > 0.55 && u < 0.92) ? 0.35 + 0.6 * Math.abs(Math.sin(i * 1.7)) : 0.08
            : 0.3 + 0.18 * Math.sin(i * 0.45) + 0.08 * Math.sin(i * 1.3);
          const h = 1.5 * a;
          return (
            <mesh key={i} geometry={roundedBox(span / N_WAVE - 0.05, 0.05, h, 0.02, 1)}
              position={[x0 + (i + 0.5) * (span / N_WAVE), 0.025, 0]}>
              <Matte color={col} />
            </mesh>
          );
        })}
      </>
    );
  }
  // subtitles: líneas de texto cerca del borde delantero
  return (
    <>
      {[[2.6, 0.2], [1.9, 0.62]].map(([w, z], i) => (
        <mesh key={i} geometry={roundedBox(w, 0.05, 0.22, 0.04, 2)} position={[0, 0.025, z]}>
          <Matte color={mix(c.body, c.card_bg, fade)} />
        </mesh>
      ))}
    </>
  );
};

export const Assembly3D: React.FC<SceneProps> = (props) => {
  const theme = requireTheme(props.theme);
  const {data, layout} = props;
  const c = theme.c;
  const {t, dur, W, H} = useClock();
  const S = slots(layout);
  const layers: string[] = data.layers ?? ['subtitles', 'music', 'voice', 'clips']; // de arriba abajo
  const head: string = data.title ?? '*FFmpeg* stitches one file';
  const output: string = data.output ?? 'final.mp4';

  // composición: la capa de abajo ya está; las demás bajan a su sitio escalonadas (≤ 0,6 s)
  const n = layers.length;
  const inP = layers.map((_, i) => (i === n - 1 ? 1 : enter(t, lay(theme, dur, (n - 1 - i) / (n - 1)), theme)));
  // énfasis: a 0,3·dur las capas se cierran (0,4 s ease-out) y el archivo se enciende
  const tMerge = Math.max(0.9, dur * 0.4);
  const merge = enter(t, tMerge, theme, theme.motion.enter_max);
  const glow = enter(t, tMerge + theme.motion.enter_max, theme);
  const gap = GAP_OPEN + (GAP_SHUT - GAP_OPEN) * merge;
  const base = 0.35;

  const vertical = layout.aspect === '9:16';
  const midY = base + ((n - 1) * gap) / 2;
  const spec = orbit({
    target: [0, midY, 0], radius: fitRadius(SLAB.w + 3.4, vertical ? 0.9 : 0.72, 30, W, H),
    elevation: 24, fov: 30, azimuth: -26 + 16 * (t / dur), W, H, cx: W / 2, cy: S.subjectY + 20,
  });
  const ppu = pxPerUnit(spec);
  const project = useProjector(spec);

  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <ThreeCanvas width={W} height={H} flat shadows={{type: THREE.VSMShadowMap}} gl={{antialias: true}}
        onCreated={props.scene3d?.gl_probe ? glProbe : undefined}>
        <CameraRig spec={spec} />
        <PaperStage theme={theme} cell={theme.grid.px / ppu} fogNear={camDist(spec) * 1.15} fogFar={camDist(spec) * 3.2} />
        <PaperLights theme={theme} span={8} />
        {layers.map((kind, i) => {
          const k = n - 1 - i; // 0 = capa de abajo
          const y = base + k * gap + (1 - inP[i]) * 0.45;
          // al fundirse, las capas se vuelven un bloque: el canto se enciende en accent
          const slabColor = mix(c.card_bg, c.accent, glow);
          return (
            <group key={kind} position={[0, y, 0]}>
              <mesh geometry={roundedBox(SLAB.w, SLAB.h, SLAB.d, 0.05)} castShadow receiveShadow>
                <Matte color={slabColor} opacity={inP[i] < 1 ? Math.max(0.001, inP[i]) : 1} />
              </mesh>
              <group position={[0, SLAB.h / 2, 0]}>
                {inP[i] > 0.01 && <Pattern kind={kind} theme={theme} fade={k === n - 1 ? 0 : merge} />}
              </group>
            </group>
          );
        })}
      </ThreeCanvas>
      <Glow theme={theme} />
      <Title theme={theme} text={head} t={t} y={S.titleY} />
      {layers.map((kind, i) => {
        const k = n - 1 - i;
        // centro de la cara superior de la capa (no el canto frontal: con la cámara en picado el canto
        // cae a la altura de la capa de abajo y las etiquetas quedaban corridas una capa)
        const p = project([-SLAB.w / 2 - 0.35, base + k * gap + (1 - inP[i]) * 0.45 + SLAB.h / 2, 0]);
        return (
          <Label key={kind} theme={theme} x={p.x} y={p.y} text={kind} align="right" opacity={inP[i] * (1 - merge)}
            size={Math.round(theme.size.body * 0.9)} color={c.body} />
        );
      })}
      {(() => {
        const p = project([SLAB.w / 2 + 0.35, midY, SLAB.d / 2]);
        return (
          <Label theme={theme} x={p.x} y={p.y} text={output} align="left" font="mono" opacity={glow}
            size={Math.round(theme.size.mono * theme.size.figure_scale)} weight={700} color={c.keyword} />
        );
      })()}
      <Sfx theme={theme} name={theme.sfx.rules.typewriter_end} at={titleEnd(theme, head)} />
      <Sfx theme={theme} name={theme.sfx.rules.card_enter} at={tMerge} />
    </AbsoluteFill>
  );
};


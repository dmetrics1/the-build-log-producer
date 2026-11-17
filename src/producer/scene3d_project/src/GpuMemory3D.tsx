// GpuMemory3D: el pico de memoria de GPU medido (METRICS.values.vram_peak_gb) sobre un módulo de 8 GB.
// Cada chip = 1 GB; los chips se llenan en accent de izquierda a derecha con el contador (ease-out,
// THEME.motion.counter). Cámara en órbita lenta; sombra suave sobre el papel.
// Equivalente 2D: x26 de scripts/test_script.scenes.js (memBar).
import React from 'react';
import {AbsoluteFill} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {
  CameraRig, Glow, Label, Matte, PaperLights, PaperStage, SceneProps, Sfx, Title, clamp, counterText, easeOut,
  camDist, fitRadius, glProbe, metric, orbit, pxPerUnit, requireTheme, roundedBox, slots, titleEnd, useClock, useProjector,
} from './paper';

const BOARD = {w: 10.6, h: 0.16, d: 2.7, y: 0.55};
const CHIP = {w: 1.06, h: 0.24, d: 1.45, gap: 0.2, z: -0.28};
const FILL0 = 0.05; // el llenado arranca casi en el frame 0 (como memBar)

export const GpuMemory3D: React.FC<SceneProps> = (props) => {
  const theme = requireTheme(props.theme);
  const {metrics, data, layout} = props;
  const c = theme.c;
  const {t, dur, W, H} = useClock();
  const S = slots(layout);

  const max: number = data.max ?? 8;
  const value = metric(metrics, 'values.vram_peak_gb', Number(data.value ?? 2.3));
  const valueText = metric(metrics, 'display.vram_peak', `${value} GB`);
  const head: string = data.title ?? 'Peak *GPU memory*';
  const p = easeOut((t - FILL0) / theme.motion.counter);
  const used = clamp(value, 0, max) * p;

  // órbita lenta y constante: 24° en toda la escena
  const vertical = layout.aspect === '9:16';
  const spec = orbit({
    target: [0, BOARD.y, 0], radius: vertical ? fitRadius(BOARD.w, 0.9, 30, W, H) : fitRadius(BOARD.w, 0.7, 30, W, H),
    elevation: vertical ? 40 : 36, fov: 30,
    // en 9:16 la placa se ve en diagonal (llena más alto del cuadro vertical)
    azimuth: (vertical ? 30 : -14) + (vertical ? 12 : 24) * (t / dur), W, H, cx: W / 2, cy: S.subjectY,
  });
  const ppu = pxPerUnit(spec);
  const project = useProjector(spec);

  const n = Math.round(max);
  const pitch = CHIP.w + CHIP.gap;
  const x0 = -((n - 1) * pitch) / 2;
  const top = BOARD.y + BOARD.h / 2;
  const left = project([-BOARD.w / 2 + 0.25, BOARD.y - BOARD.h / 2, BOARD.d / 2]);
  const right = project([BOARD.w / 2 - 0.25, BOARD.y - BOARD.h / 2, BOARD.d / 2]);
  const figPx = Math.round(theme.size.mono * 1.5 * theme.size.figure_scale);

  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <ThreeCanvas width={W} height={H} flat shadows={{type: THREE.VSMShadowMap}} gl={{antialias: true}}
        onCreated={props.scene3d?.gl_probe ? glProbe : undefined}>
        <CameraRig spec={spec} />
        <PaperStage theme={theme} cell={theme.grid.px / ppu} fogNear={camDist(spec) * 1.15} fogFar={camDist(spec) * 3.2} />
        <PaperLights theme={theme} span={8} target={[0, 0, 0]} />
        {/* placa del módulo: tarjeta blanca */}
        <mesh geometry={roundedBox(BOARD.w, BOARD.h, BOARD.d, 0.07)} position={[0, BOARD.y, 0]} castShadow receiveShadow>
          <Matte color={c.card_bg} />
        </mesh>
        {/* contactos en el borde delantero (pista) */}
        {Array.from({length: 34}, (_, i) => (
          <mesh key={i} geometry={roundedBox(0.16, 0.02, 0.34, 0.008, 1)}
            position={[-BOARD.w / 2 + 0.55 + i * ((BOARD.w - 1.1) / 33), top + 0.01, BOARD.d / 2 - 0.26]} receiveShadow>
            <Matte color={c.track} />
          </mesh>
        ))}
        {/* 8 chips de 1 GB: pista vacía + parte usada en accent (crece desde la izquierda) */}
        {Array.from({length: n}, (_, i) => {
          const f = clamp(used - i);
          const x = x0 + i * pitch;
          const lift = 0.05 * easeOut(f * 2);
          return (
            <group key={i} position={[x, top + CHIP.h / 2 + lift, CHIP.z]}>
              <mesh geometry={roundedBox(CHIP.w, CHIP.h, CHIP.d, 0.05)} castShadow receiveShadow>
                <Matte color={c.track} />
              </mesh>
              {f > 0.001 && (
                <mesh geometry={roundedBox(CHIP.w * f + 0.004, CHIP.h + 0.006, CHIP.d + 0.006, Math.min(0.05, (CHIP.w * f) / 2))}
                  position={[-CHIP.w / 2 + (CHIP.w * f) / 2, 0, 0]} castShadow>
                  <Matte color={c.accent} />
                </mesh>
              )}
            </group>
          );
        })}
      </ThreeCanvas>
      <Glow theme={theme} />
      <Title theme={theme} text={head} t={t} y={S.titleY} />
      {/* escala: 0 y 8 GB anclados a los extremos de la placa (se mueven con la órbita) */}
      <Label theme={theme} x={left.x} y={left.y + 46} text="0" font="mono" color={c.muted} />
      <Label theme={theme} x={right.x} y={right.y + 46} text={`${max} GB`} font="mono" color={c.muted} />
      {/* lectura: la cifra medida (contador) y el total */}
      <div style={{position: 'absolute', left: 0, right: 0, top: S.readoutY, transform: 'translateY(-50%)', textAlign: 'center'}}>
        <span style={{fontFamily: `'${theme.family.mono}'`, fontWeight: 700, fontSize: figPx, color: c.accent}}>
          {counterText(valueText, p)}
        </span>
        <span style={{fontFamily: `'${theme.family.body}'`, fontWeight: 500, fontSize: theme.size.body, color: c.muted, marginLeft: 22}}>
          {`of ${max} GB`}
        </span>
      </div>
      <Sfx theme={theme} name={theme.sfx.rules.typewriter_end} at={titleEnd(theme, head)} />
      <Sfx theme={theme} name={theme.sfx.rules.number_end} at={FILL0 + theme.motion.counter} />
    </AbsoluteFill>
  );
};

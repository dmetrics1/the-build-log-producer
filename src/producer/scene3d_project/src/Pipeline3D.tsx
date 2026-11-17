// Pipeline3D: los cinco agentes como bloques en fila; un paquete (accent) recorre el flujo y el
// Productor se eleva y se enciende en accent. Equivalente 2D: x05 de scripts/test_script.scenes.js.
// Geometría simple y propia (cajas, toros, conos): nada de personajes.
import React from 'react';
import {AbsoluteFill} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import * as THREE from 'three';
import {
  CameraRig, Glow, Label, Matte, PaperLights, PaperStage, SceneProps, Sfx, Theme, Title, clamp, easeOut, enter,
  camDist, fitRadius, glProbe, lay, metric, mix, orbit, parseKeywords, pxPerUnit, requireTheme, roundedBox, slots, titleEnd, useClock,
  useProjector,
} from './paper';

const BLOCK = {w: 1.7, h: 1.0, d: 1.7};
const PITCH = 2.75;

// Glifos de cada agente sobre su bloque (coordenadas locales: y = 0 es la cara superior)
const Glyph: React.FC<{kind: string; color: string; paper: string}> = ({kind, color, paper}) => {
  const m = <Matte color={color} />;
  switch (kind) {
    case 'Researcher': // lupa
      return (
        <group rotation={[0, 0.35, 0]}>
          <mesh position={[-0.08, 0.5, 0]} castShadow>
            <torusGeometry args={[0.3, 0.075, 16, 40]} />{m}
          </mesh>
          <mesh position={[0.22, 0.13, 0]} rotation={[0, 0, 0.75]} castShadow>
            <cylinderGeometry args={[0.065, 0.065, 0.42, 16]} />{m}
          </mesh>
        </group>
      );
    case 'Writer': // hoja con líneas de texto
      return (
        <group rotation={[-0.25, 0.2, 0]} position={[0, 0.12, 0]}>
          <mesh geometry={roundedBox(0.8, 0.06, 1.0, 0.025)} castShadow>{m}</mesh>
          {[0.28, 0.08, -0.12, -0.32].map((z, i) => (
            <mesh key={i} geometry={roundedBox(i === 3 ? 0.34 : 0.56, 0.03, 0.07, 0.012, 1)} position={[i === 3 ? -0.11 : 0, 0.045, -z]}>
              <Matte color={paper} />
            </mesh>
          ))}
        </group>
      );
    case 'Producer': // botón de reproducir: prisma triangular
      return (
        <mesh position={[0.05, 0.14, 0]} rotation={[0, Math.PI / 2, 0]} castShadow>
          <cylinderGeometry args={[0.46, 0.46, 0.24, 3]} />{m}
        </mesh>
      );
    case 'Publisher': // flecha hacia arriba
      return (
        <group>
          <mesh position={[0, 0.25, 0]} castShadow>
            <cylinderGeometry args={[0.09, 0.09, 0.5, 20]} />{m}
          </mesh>
          <mesh position={[0, 0.68, 0]} castShadow>
            <coneGeometry args={[0.28, 0.4, 28]} />{m}
          </mesh>
        </group>
      );
    default: // Analyst: barras crecientes
      return (
        <group>
          {[0.32, 0.56, 0.82].map((h, i) => (
            <mesh key={i} geometry={roundedBox(0.2, h, 0.2, 0.03)} position={[-0.3 + i * 0.3, h / 2, 0]} castShadow>{m}</mesh>
          ))}
        </group>
      );
  }
};

// Flecha plana sobre el papel entre dos bloques
const Connector: React.FC<{theme: Theme; x0: number; x1: number}> = ({theme, x0, x1}) => {
  const len = x1 - x0 - 0.3;
  return (
    <group position={[(x0 + x1) / 2 - 0.12, 0.02, 0]}>
      <mesh geometry={roundedBox(len, 0.04, 0.09, 0.015, 1)} receiveShadow>
        <Matte color={theme.c.muted} />
      </mesh>
      <mesh position={[len / 2 + 0.08, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <cylinderGeometry args={[0.17, 0.17, 0.04, 3]} />
        <Matte color={theme.c.muted} />
      </mesh>
    </group>
  );
};

export const Pipeline3D: React.FC<SceneProps> = (props) => {
  const theme = requireTheme(props.theme);
  const {metrics, data, layout} = props;
  const c = theme.c;
  const {t, dur, W, H} = useClock();
  const S = slots(layout);
  const agents: string[] = data.agents ?? ['Researcher', 'Writer', 'Producer', 'Publisher', 'Analyst'];
  const hi: number = data.highlight ?? agents.indexOf('Producer');
  const head: string = data.title ?? 'Five agents, one *Producer*';

  // composición: el primer bloque ya está (frame 0); los demás suben del papel escalonados (≤ 0,6 s)
  const rise = agents.map((_, i) => (i === 0 ? 1 : enter(t, lay(theme, dur, i / (agents.length - 1)), theme)));
  // énfasis con la narración: el paquete viaja hasta el Productor; el Productor se eleva y se enciende
  const tPacket = 0.75, tArrive = 0.75 + 0.32 * hi;
  const tLift = tArrive;
  const lift = enter(t, tLift, theme, theme.motion.enter_max);
  const packetX = (Math.min(1, clamp((t - tPacket) / (tArrive - tPacket))) * hi - (agents.length - 1) / 2) * PITCH;
  const showPacket = t >= tPacket && t < tArrive + 0.05;
  const tCost = tLift + 0.55;
  const cost = enter(t, tCost, theme);

  const vertical = layout.aspect === '9:16';
  const spec = orbit({
    target: [0, 0.5, 0], radius: fitRadius(PITCH * 4 + BLOCK.w, vertical ? 0.86 : 0.74, 30, W, H), elevation: 27, fov: 30,
    azimuth: 9 - 18 * (t / dur), W, H, cx: W / 2, cy: S.subjectY,
  });
  const ppu = pxPerUnit(spec);
  const project = useProjector(spec);
  const xs = agents.map((_, i) => (i - (agents.length - 1) / 2) * PITCH);

  const software = metric(metrics, 'display.software', '$0');
  const electricity = metric(metrics, 'display.electricity', '');

  return (
    <AbsoluteFill style={{backgroundColor: c.bg}}>
      <ThreeCanvas width={W} height={H} flat shadows={{type: THREE.VSMShadowMap}} gl={{antialias: true}}
        onCreated={props.scene3d?.gl_probe ? glProbe : undefined}>
        <CameraRig spec={spec} />
        <PaperStage theme={theme} cell={theme.grid.px / ppu} fogNear={camDist(spec) * 1.15} fogFar={camDist(spec) * 3.2} />
        <PaperLights theme={theme} span={9} />
        {xs.slice(0, -1).map((x, i) => (
          <Connector key={i} theme={theme} x0={x + BLOCK.w / 2} x1={xs[i + 1] - BLOCK.w / 2} />
        ))}
        {agents.map((a, i) => {
          const isHi = i === hi;
          const k = isHi ? lift : 0;
          const y = -BLOCK.h * (1 - rise[i]) + BLOCK.h / 2 + 0.55 * k;
          const blockColor = isHi ? mix(c.card_bg, c.accent, k) : c.card_bg;
          const glyphColor = isHi ? mix(c.body, c.card_bg, k) : c.body;
          return (
            <group key={a} position={[xs[i], y, 0]}>
              <mesh geometry={roundedBox(BLOCK.w, BLOCK.h, BLOCK.d, 0.16)} castShadow receiveShadow>
                <Matte color={blockColor} />
              </mesh>
              <group position={[0, BLOCK.h / 2, 0]}>
                <Glyph kind={a} color={glyphColor} paper={blockColor} />
              </group>
            </group>
          );
        })}
        {showPacket && (
          <mesh geometry={roundedBox(0.3, 0.3, 0.3, 0.06)} position={[packetX, 0.2, 0.0]} castShadow>
            <Matte color={c.accent} />
          </mesh>
        )}
      </ThreeCanvas>
      <Glow theme={theme} />
      <Title theme={theme} text={head} t={t} y={S.titleY} />
      {agents.map((a, i) => {
        const p = project([xs[i], 0, BLOCK.d / 2 + 0.15]);
        const isHi = i === hi;
        return (
          <Label key={a} theme={theme} x={p.x} y={p.y + 40} text={a} opacity={rise[i]}
            color={isHi ? mix(c.body, c.keyword, lift) : c.body} size={Math.round(theme.size.body * 0.9)} />
        );
      })}
      {/* costo por video: cifras en cost (accent3), palabras en muted */}
      <div style={{
        position: 'absolute', left: 0, right: 0, top: S.readoutY, textAlign: 'center', opacity: cost,
        transform: `translateY(calc(-50% + ${(1 - cost) * 24}px))`, fontFamily: `'${theme.family.body}'`,
        fontWeight: 500, fontSize: theme.size.body, color: c.muted,
      }}>
        {parseKeywords(`Per video: *${software}* software` + (electricity ? ` · *${electricity}* electricity` : '')).map((s, i) => (
          <span key={i} style={s.key ? {fontFamily: `'${theme.family.mono}'`, fontWeight: 700, color: c.cost} : {}}>{s.text}</span>
        ))}
      </div>
      <Sfx theme={theme} name={theme.sfx.rules.typewriter_end} at={titleEnd(theme, head)} />
      <Sfx theme={theme} name={theme.sfx.rules.card_enter} at={tLift} />
    </AbsoluteFill>
  );
};

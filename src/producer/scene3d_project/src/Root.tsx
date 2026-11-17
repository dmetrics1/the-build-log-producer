// Registro de composiciones. Tamaño, fps y duración salen de las props (scene3d.py): 1920×1080 o
// 1080×1920 (Shorts), 30 fps y exactamente los frames de la narración de la escena.
import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import {GpuMemory3D} from './GpuMemory3D';
import {Pipeline3D} from './Pipeline3D';
import {Assembly3D} from './Assembly3D';
import {PaperFonts, SceneProps} from './paper';

const DEFAULTS: SceneProps = {
  theme: null,
  fonts: [],
  metrics: null,
  data: {},
  layout: {aspect: '16:9', width: 1920, height: 1080, fps: 30, frames: 180, reserved: []},
  scene3d: {gl_probe: false, supersample: 1},
};

const calc: CalculateMetadataFunction<SceneProps> = ({props}) => ({
  durationInFrames: props.layout.frames,
  fps: props.layout.fps,
  width: props.layout.width,
  height: props.layout.height,
});

const withFonts = (C: React.FC<SceneProps>): React.FC<SceneProps> => (p) => (
  <PaperFonts fonts={p.fonts}>
    <C {...p} />
  </PaperFonts>
);

// id de composición -> componente. Un futuro [EXPLAIN3D: ... | comp=Pipeline3D] elige de aquí.
export const COMPOSITIONS: Record<string, React.FC<SceneProps>> = {
  GpuMemory3D: withFonts(GpuMemory3D),
  Pipeline3D: withFonts(Pipeline3D),
  Assembly3D: withFonts(Assembly3D),
};

export const Root: React.FC = () => (
  <>
    {Object.entries(COMPOSITIONS).map(([id, C]) => (
      <Composition key={id} id={id} component={C} defaultProps={DEFAULTS} calculateMetadata={calc}
        durationInFrames={180} fps={30} width={1920} height={1080} />
    ))}
  </>
);

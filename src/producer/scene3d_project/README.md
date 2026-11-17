# scene3d: 3D explainer scenes (prototype)

Three.js scenes rendered by [Remotion](https://www.remotion.dev) through `@remotion/three`
(React Three Fiber), in the channel's **paper** theme. A complement to explainroo (2D diagrams),
not a replacement. **Status: prototype, not wired into `produce`.** The owner approves before integration.

## When to use 3D

Only when depth explains something a flat diagram does not: layers that stack, structure seen
from more than one side, flow between physical-looking parts. If a 2D explainroo diagram explains it
equally, the 2D one wins: it renders faster and is easier to maintain. Never use 3D as decoration.

## Files

| file | role |
| --- | --- |
| `package.json`, `package-lock.json` | exact pinned versions (Remotion 4.0.540, three 0.187.0, R3F 9.8.2, React 19.3.1) |
| `src/index.ts`, `src/Root.tsx` | registers the compositions; size, fps and duration come from the props |
| `src/paper.tsx` | shared paper pieces: fonts, typewriter title, labels, glow, camera orbit, paper floor with the 48 px grid, lights, soft (VSM) shadows |
| `src/GpuMemory3D.tsx` | peak GPU memory on an 8 GB module (1 chip = 1 GB), value from METRICS |
| `src/Pipeline3D.tsx` | the five agents as blocks; a packet travels the flow; the Producer lifts and turns accent |
| `src/Assembly3D.tsx` | clips, voice, music and subtitles as stacked layers that merge into `final.mp4` |

**No colour, font or timing is written here.** Everything comes from `src/producer/theme_paper.py`
(`scenes_theme()`), injected by `src/producer/scene3d.py` as input props (`theme`, `fonts`, `metrics`,
`data`, `layout`). Text is an HTML layer on top of the WebGL canvas (crisp fonts, same as explainroo);
labels attached to 3D objects are projected with the same camera every frame.

## How it runs (Python side)

`producer.scene3d.render_scene3d(scene, cfg, workdir, cache_dir, metrics)` mirrors `explain.render_explain`:

1. `ensure_deps`: `npm ci` into `%LOCALAPPDATA%\tbl-tmp\cache\scene3d\deps-<hash of package files>\`
   and `remotion browser ensure` (Chrome Headless Shell into `node_modules\.remotion`). Nothing lands in the synced folder.
2. `ensure_bundle`: copies this template plus the theme fonts and SFX (`public/assets/...`) into
   `deps-<hash>\projects\<key>\` and runs `remotion bundle` once per template/asset hash.
3. `remotion render <bundle> <Composition> --props=props.json --gl=angle ...` with a timeout and 3 attempts.
4. Normalises with the same `COLOR_VF` / `COLOR_ARGS` and 48 kHz audio as every other clip; content-hash cache
   in `cache\scene3d\clips\`.

Demo: `python -m producer.scene3d demo` (writes `runs/scene3d_demo/`). Benchmark only:
`python -m producer.scene3d demo --bench --force --gl swangle --only Pipeline3D`.

Formats: `16:9` (1920×1080, nothing below y = 864: burned-in subtitles) and `9:16` (1080×1920 for Shorts:
the karaoke band around y = 960 and the bottom 20 % stay empty).

## GPU / OpenGL in headless Chrome

Default: `--gl=vulkan` (ANGLE over Vulkan), which runs on the **RTX 5050** (~0.9 GB VRAM with 4 tabs).
`--gl=angle` (D3D11) uses the Optimus default adapter, which is the Intel UHD iGPU here: a little slower, and
it is the fallback on the last attempt. `egl` and `angle-egl` fall back to the Microsoft Basic Render Driver
(software), and `swangle` is SwiftShader (about 9× slower). Measured table: `runs/scene3d_demo/README.md`.

## Future `[EXPLAIN3D: ...]` tag (not implemented)

```
[EXPLAIN3D: the five agents as blocks, the Producer lifts | comp=Pipeline3D | highlight=Producer]
[EXPLAIN3D: peak GPU memory on an 8 GB module | comp=GpuMemory3D | metrics=vram_peak]
[EXPLAIN3D: four inputs stacked as layers, merging into final.mp4 | comp=Assembly3D]
```

- `scenes.py` would parse it like `[EXPLAIN: ...]` (new kind `EXPLAIN3D`), keeping `label`, `display_text`,
  `keywords` and `braces`; `comp=` picks the composition registered in `src/Root.tsx`
  (`COMPOSITIONS` in `scene3d.py`); other `| k=v` options go to `data` (e.g. `highlight`, `title`).
- The title would come from the narration's `*keyword*` sentence, as in the 2D scenes; `metrics=` keeps the same
  check against the manifest (`metrics.check_script`).
- The pipeline would call `scene3d.render_scene3d` where it calls `explain.render_explain`, and the
  manifest would record `render_s`, `gl_renderer` and the VRAM figures per scene.

## License

Remotion uses its own license: **free for individuals and for companies of up to 3 people**
(non-profits too); larger companies need a company license. The Build Log (one owner) qualifies for the
free tier. Check https://www.remotion.dev/license before the team grows. three.js, React and React Three
Fiber are MIT.

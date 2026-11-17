# The Build Log — Producer

**Script to MP4 on an 8 GB GPU: local TTS, alignment and diagram rendering.**

This is the Producer agent of [The Build Log](https://www.youtube.com/@thebuildlogdm), a faceless
YouTube channel about applied AI and automation. You give it a Markdown script with scene tags; it
gives you back a finished 1080p video:

- **Voice**: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), running locally on the GPU.
- **Word timing**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) `large-v3-turbo`. The
  words come from the script and only the timing comes from Whisper, so captions never say "12" when the
  script says "twelve".
- **Diagrams**: `[EXPLAIN]` scenes are drawn in code and rendered with
  [explainroo](https://www.npmjs.com/package/explainroo) (Node, headless Chromium). An optional 3D
  prototype uses Remotion + Three.js.
- **Screen scenes**: `[SCREEN]` scenes use an OBS recording, a rendered panel (a file, a terminal capture or
  an image), or a placeholder with a slow zoom.
- **Callouts and captions**: keyword callouts are burned in over screen scenes. The full transcript is
  written to `final.srt` as closed captions. A word-by-word karaoke caption module for vertical Shorts
  (`karaoke.py`) is included, but the CLI doesn't use it yet.
- **Assembly**: FFmpeg, with music ducking, generated SFX (tick, swoosh, pop) and an automatic hook built
  from the scenes you tag.
- **Manifest**: every run writes `runs/<date>_<slug>/manifest.json` with models, timings, VRAM per stage
  and the estimated cost, so the run can be reproduced and checked.

Nothing gets published from here. A run ends with `approved=false` until a human watches the video and
runs `approve`.

## Measured on our laptop

These are cold-run numbers (no cache) for the 2 min 46 s example video in `scripts/test_script.md`, read
from its `manifest.json` (2026-11-16):

| | |
| --- | --- |
| Hardware | RTX 5050 Laptop GPU, 8 GB VRAM; Windows 11; Python 3.11; PyTorch 2.11 + CUDA 12.8 |
| Output | 166 s, 1920×1080 @ 30 fps, H.264 + AAC, 12.1 MB; 46 scenes, 29 rendered diagrams |
| Script → verified MP4 | **2 min 41 s** wall clock (161 s) |
| Slowest stages | diagrams 79.7 s (29 scenes, 3 in parallel, on the CPU) · assembly 35.5 s · TTS 20.2 s · alignment 9.9 s |
| Peak VRAM | **2.3 GB** (Whisper alignment); TTS 0.9 GB |
| Software / API cost | **$0** |
| Electricity | ~0.006 kWh ≈ **$0.0013** (estimated from 140 W × run time × $0.22/kWh, not metered) |
| Re-run with caches | 67 s (narration and diagrams reused) |

## Requirements

- Windows 11 (the only platform tested; see *Limitations*)
- An NVIDIA GPU with 8 GB of VRAM (about 2.3 GB is used at peak), with a recent driver
- [conda](https://docs.conda.io/) (Miniconda or Anaconda), with **Python 3.11**
- **FFmpeg** and **ffprobe** on your `PATH`
- **Node.js 20+** (`npx` runs explainroo; `npm` is used only by the optional 3D scenes)
- About 3 GB of disk for the models (Kokoro and Whisper are downloaded from Hugging Face)

## Installation

```powershell
git clone https://github.com/dmetrics1/the-build-log-producer.git
cd the-build-log-producer

conda create -n tbl python=3.11 -y
conda activate tbl

# 1. PyTorch first, with CUDA 12.8+ (RTX 50-series GPUs need cu128 or newer)
pip install torch==2.11.0 torchaudio==2.11.0 --index-url https://download.pytorch.org/whl/cu128

# 2. Everything else, plus the package itself
pip install -r requirements.txt
pip install -e .

# 3. Configuration
copy config.example.toml config.toml

# 4. Check the machine and download the models
python -m producer doctor --fetch
python -m producer doctor          # every line should say OK
```

`doctor` checks Python, the GPU and CUDA, FFmpeg, Node/explainroo, the models, OBS (optional, only for
recordings), the output folders and their free space. You can
optionally create a `.env` with `HF_HOME` (the model cache) and `TBL_TMP_DIR` (intermediate files;
the default is `%LOCALAPPDATA%\tbl-tmp`).

## Usage

```powershell
python -m producer produce scripts\test_script.md      # -> runs\<date>_test\final.mp4 + final.srt + manifest.json
python -m producer produce scripts\test_script.md --variant fast
python -m producer approve <run_id> --by "your name"     # only after you have watched the video
```

## Script format

A script is a Markdown file with YAML front matter. Each tag starts a scene, and the text under the tag is
that scene's narration (8 to 12 words, which is 3 to 5 seconds). EXPLAIN scenes are drawn by functions in
a sibling file, `<script>.scenes.js`.

```markdown
---
title: "This Video Made Itself: Script to MP4 for $0 on an 8GB GPU"
slug: test
voice: am_echo
speed: 1.05
---

# 0:00 Hook: result and numbers

[SCREEN: this finished video playing in a media player | hook | in=0.5 | speed=2.5]
No camera. No microphone. No video editor.

[EXPLAIN: one huge number, "$0", labeled "software cost" | metrics=software]
This video cost *{$0|zero dollars}* in software.

[SCREEN: terminal running the doctor | show=terminal | capture=assets/screens/doctor_ok.txt | mark=0 FAIL]
Every check comes back *green* before the first frame is rendered.
```

| syntax | meaning |
| --- | --- |
| `# 0:10 Section` | section heading (timestamp and purpose). Not narrated |
| `[SCREEN: description]` | screen scene. With no source, you get a placeholder with a slow zoom |
| `\| src=rec.mkv in=12 out=45 zoom=x,y,w,h` | use an OBS recording, sped up to fit (at most 4×) |
| `\| show=file path=… find=… lines=… hl=…` | render a source file as a code panel with highlighted lines |
| `\| show=terminal capture=….txt mark=…` | render a terminal capture with marked lines |
| `\| show=image path=….png` | still image with a slow zoom |
| `[EXPLAIN: description]` | diagram scene drawn in `<script>.scenes.js` |
| `\| id=x05` | fixed id of the drawing in `scenes.js` |
| `\| metrics=software,electricity` | the numbers in the narration are checked against the manifest |
| `\| scene3d=Pipeline3D` | render the scene in 3D (prototype; use 1–2 per video at most) |
| `\| hook` / `\| hook_source` | build the opening hook automatically from the tagged scenes |
| `\| keep` | keep this visual even if the scene is merged for being too short |
| `*word*` | keyword: shown in the accent colour, and becomes the callout on screen scenes |
| `[CALLOUT: text with *key*]` | replaces the automatic callout for the next sentence. Not narrated |
| `{on screen\|spoken}` | what captions show vs what the voice says (`{$0\|zero dollars}`) |
| `<!-- … -->` | comment. Not narrated |
| `# Metadata` | everything after this line is ignored by the voice (title, description, chapters) |

The full reference (in Spanish) is the comment block at the top of `scripts/test_script.md`.
`config/pronounce.toml` fixes how the voice pronounces single words.

## Layout

```
src/producer/        pipeline (parse → tts → timeline → align → screens → explain → hook → music
                     → subtitles → assemble → verify), doctor, approve, theme, karaoke
src/producer/scene3d_project/   Remotion + Three.js compositions (optional 3D scenes)
assets/brand/        design tokens of the "paper" theme
assets/fonts/        Inter, Space Grotesk, JetBrains Mono (SIL OFL 1.1, licences included)
assets/sfx/          tick / swoosh / pop, generated by assets/sfx/generate.py (CC0)
scripts/             example script + its diagrams
```

## Limitations

- **Tested on Windows 11 only.** Parts of the code are Windows-specific: the PATH is re-read from the
  registry, and paths assume `%LOCALAPPDATA%` and the win64 Chrome Headless Shell for 3D. Linux and macOS
  may need small changes.
- **The example script is ours.** Its SCREEN panels refer to terminal captures and images in
  `assets/screens/`, and one of them shows a run manifest. None of these are in this repo, so you need to
  add your own captures or remove the `show=` parameters (the scene then falls back to a placeholder).
- **No music included.** Add licensed tracks to `assets/music/` and document each one in
  `assets/music/music.md` (file, title, artist, license, source). With no tracks, a generated tone is
  used and marked as a placeholder in the manifest.
- **Diagrams are code.** Each EXPLAIN scene needs a drawing function in `<script>.scenes.js`. The
  Producer doesn't invent visuals from the description.
- **Screen recordings are manual** (OBS). Without them, SCREEN scenes are panels or placeholders.
- **English voice only** (Kokoro `am_echo`). Other Kokoro voices and languages were not tested here.
- **explainroo can hang if FFmpeg is not visible** to its process. The Producer passes absolute FFmpeg
  paths and stops each attempt after 90 s, and 3 failures stop the run.
- **The 3D scenes are a prototype**, and the first run downloads Remotion with `npm ci`.
- **The numbers above come from one laptop and one script.** The electricity cost is an estimate, not a
  measurement.
- Many code comments and some messages are in Spanish.

## Links

- Channel: <https://www.youtube.com/@thebuildlogdm>
- Author: Daniel Molina — <https://personal-landing-beta-neon.vercel.app/>

## License

Code: [MIT](LICENSE) © 2026 Daniel Molina. Fonts: SIL Open Font License 1.1 (`assets/fonts/OFL-*.txt`).
Sound effects: CC0 1.0 (`assets/sfx/README.md`).

---
title: "This Video Made Itself: Script to MP4 for $0 on an 8GB GPU"
affiliate_links: []   # extra a lo detectado: el Productor inserta la divulgación (texto + voz, primeros 30 s) si el guion menciona un programa de config/affiliates.toml o si esta lista no está vacía
slug: test
voice: am_echo
speed: 1.05
music: wind_riders.mp3
target_seconds: 180
---

<!--
FORMATO (lo lee src/producer/scenes.py; los comentarios HTML no se narran)
- "# ..."            encabezado de sección: marca de tiempo y función de retención. No se narra.
- "| hook | in=0.5 | speed=2.6" en un [SCREEN]: gancho automático hecho con los planos de las escenas
                     marcadas "| hook_source" (si no hay, la EXPLAIN con la cifra principal).
- "[SCREEN: ...]"    escena de pantalla. Con "| src=grabación in=12 out=45 zoom=x,y,w,h" usa la grabación
                     de OBS (acelerada hasta encajar, máx. 4x); sin src, placeholder con Ken Burns.
- "[EXPLAIN: ...]"   escena explicativa renderizada con explainroo (dibujo en test_script.scenes.js).
- "| keep"           si la escena se fusiona por durar menos de 2,5 s, se conserva su visual.
- "| id=xcc"         en un [EXPLAIN]: id fijo de la escena en test_script.scenes.js (no corre la numeración x01, x02…).
- "| scene3d=Comp"   en un [EXPLAIN]: la escena se renderiza en 3D (src/producer/scene3d.py, composiciones
                     GpuMemory3D, Pipeline3D, Assembly3D). Solo si la profundidad explica algo; máx. 1–2 por video.
- "music: pista.mp3" en el front matter elige la música (documentada en assets/music/music.md).
- Texto tras la etiqueta = narración de esa escena, 8 a 12 palabras (3–5 s a ~145 ppm).
- *palabra*          palabra clave (una por frase): en escenas SCREEN genera el callout quemado (la clave en
                     azul accent + 2–4 palabras vecinas de su oración); en EXPLAIN no se quema texto.
- [CALLOUT: texto con *clave*]  línea dentro de una escena, antes de la frase a la que se aplica: reemplaza el
                     callout automático de la frase que contiene la siguiente palabra narrada (3–6 palabras,
                     una línea). No se narra. Solo se quema si esa frase cae en una escena SCREEN.
- {pantalla|voz}     lo que se muestra (final.srt y callouts) | lo que dice la voz.
- Subtítulos: final.srt lleva la transcripción completa (closed captions, los sube el Publicador); el video
                     long-form solo quema callouts.
- "# Metadata"       desde aquí nada se narra.
-->

# 0:00 Hook: result and numbers

[SCREEN: this finished video playing in a media player, 1920x1080 and its length visible | hook | in=0.5 | speed=2.5]
No camera. No microphone. No video editor.

[EXPLAIN: one huge number, "$0", labeled "software cost" | metrics=software]
This video cost *{$0|zero dollars}* in software.

[EXPLAIN: laptop with a GPU chip labeled "8 GB"]
It ran on an *{8 GB|eight gigabyte}* laptop GPU.

[EXPLAIN: a memory bar from 0 to 8 GB that never passes 3 GB | keep]
It never used more than *{3|three}*.

# 0:10 What you will see

[SCREEN: terminal running "python -m producer doctor", every line OK | show=terminal | capture=assets/screens/doctor_ok.txt]
A script goes in. A finished *MP4* comes out.

[EXPLAIN: arrow from a file "script.md" to a file "final.mp4", stages as dots along the arrow]
Here is every stage, and what each one costs.

[EXPLAIN: five boxes in a row: Researcher, Writer, Producer, Publisher, Analyst; Producer lit]
The channel has five AI agents. Today we test one: the *Producer*.

# 0:24 First demo: the voice

[SCREEN: scripts/test_script.md open in the editor, the scene tags highlighted | show=file | path=scripts/test_script.md | find=# 0:10 | highlight=SCREEN,EXPLAIN]
It starts with a script. Every scene has a *tag*.

[EXPLAIN: two cards side by side: "SCREEN = real recording" and "EXPLAIN = animated diagram"]
Screen means a real recording. Explain means a diagram, like this one.

[SCREEN: terminal generating audio with Kokoro, voice "am_echo" visible | show=terminal | capture=assets/screens/kokoro_am_echo.txt | highlight=am_echo | mark=run 2]
The voice is *{Kokoro|/kˈOkOɹO/}*. A small model, running locally.

[EXPLAIN: timeline: 7.9 seconds of speech generated in 1.8 seconds]
It speaks more than *{4x|four times}* faster than real time.

[EXPLAIN: memory gauge filling to 0.9 of 8 GB]
And it needs under *{1 GB|one gigabyte}* of video memory.

# 0:45 Re-hook (25%): unexpected result

[SCREEN: our test sentence with the word "twelve" next to Whisper's output with "12" | show=terminal | capture=assets/screens/whisper_twelve.txt | highlight=twelve,'12' | wrap]
Then something unexpected. We wrote the word *twelve*.

[EXPLAIN: the word "twelve" turns into "12", with a red mismatch mark]
Whisper heard it perfectly, and wrote it in *digits*.

[EXPLAIN: two tracks: script words on top, Whisper words below, one pair flagged red]
So the subtitles would not match the script.

[SCREEN: src/producer/align.py, the docstring that explains the fix highlighted | show=file | path=src/producer/align.py | lines=1-16 | hl=3-4]
The fix: words come from the script. Only the *timing* comes from Whisper.

[EXPLAIN: a word timeline, each word with its start and end time]
Every word gets a start and an *end*.

[EXPLAIN: zoom on one word: "1.44 s → 1.74 s"]
Timed to the *hundredth* of a second.

# 1:07 How the picture is built

[SCREEN: explainroo rendering in the terminal, frame counter rising | show=terminal | capture=assets/screens/explainroo_render.txt | mark=frames done]
Diagrams come from *explainroo*, an open-source tool that draws with code.

[EXPLAIN: processor icon lit, graphics card icon dimmed, label "no GPU needed"]
It runs on the processor. The graphics card stays *free*.

[SCREEN: a still frame with a slow zoom, labeled "screen recording goes here" | show=image | path=assets/screens/still_agents.png | title=still frame + slow zoom (until the OBS recording exists)]
Screen scenes are placeholders for now: a slow zoom over a still.

[EXPLAIN: a red recording dot, arrow to "real demo"]
Next week they become real *screen recordings*.

[EXPLAIN: a clock face; a tick every 3 to 5 seconds swaps the picture]
The picture changes every *{3–5 s|three to five seconds}*. That holds attention.

[EXPLAIN: a large on-screen callout "one word in blue" with "blue" in the accent colour; under it a CC closed-captions icon | id=xcc]
Key phrases appear on screen, one word in *blue*. The full transcript goes up as closed *captions*, so YouTube can index it.

[EXPLAIN: two waveforms: voice on top, music below dipping whenever the voice speaks]
Music sits under the voice, and *drops* when it speaks.

[EXPLAIN: four inputs, clips, voice, music, subtitles, merging into one file | scene3d=Assembly3D]
*FFmpeg* stitches it all into one file.

[EXPLAIN: a badge "1920×1080 · 30 fps"]
*{1080p|Ten eighty p}*, thirty frames per second.

# 1:43 Where the files live

[SCREEN: File Explorer: the local temp folder filling with files | show=terminal | capture=assets/screens/tmp_cache_listing.txt]
All the messy files go to a local *temp* folder.

[EXPLAIN: two folders: "temp (local)" with many files, "runs (synced)" with two files]
Only the final results move to the synced project folder.

[EXPLAIN: one arrow labeled "rename: all or nothing"]
The move is one *rename*. The cloud never sees a half-written file.

# 1:56 Re-hook (65%): failure and fix

[SCREEN: doctor output with two red FAIL lines: "ffmpeg: not in PATH", "ffprobe: not in PATH" | show=terminal | capture=assets/screens/doctor_fail_2026-11-16.txt]
Then a failure. Our doctor said FFmpeg was *missing*.

[SCREEN: File Explorer showing ffmpeg.exe in its install folder | show=terminal | capture=assets/screens/ffmpeg_folder.txt | highlight=ffmpeg.exe | wrap]
It was installed. We had just *checked*.

[SCREEN: a terminal with a refreshed path where "ffmpeg -version" prints its version | show=terminal | capture=assets/screens/ffmpeg_version.txt | mark=ffmpeg version]
With a *refreshed* path, the same command worked.

[EXPLAIN: a terminal holding an old list of paths; the new FFmpeg entry missing from it]
The terminal opened before the install. Its path list was *stale*.

[EXPLAIN: timeline: "terminal opened", then "FFmpeg installed"; the terminal never sees the second event]
Windows hands a program its path only when it *opens*.

[SCREEN: src/producer/config.py, the function that rereads the Windows path | show=file | path=src/producer/config.py | find=def _refresh_windows_path | n=20 | mark=def _refresh_windows_path]
The fix: the pipeline rereads the Windows path when it starts.

[SCREEN: doctor run again in the same old terminal, ffmpeg now OK | show=terminal | capture=assets/screens/doctor_ok.txt | mark=OK    ffmpeg,OK    ffprobe]
Same old terminal, no restart. This time, every tool was *found*.

[SCREEN: doctor output, "16 OK, 1 WARN, 0 FAIL" | show=terminal | capture=assets/screens/doctor_ok.txt | lines=1,17-23 | size=36 | mark=0 FAIL]
*{17|Seventeen}* checks. Zero failures.

[EXPLAIN: a rule card: "3 failures → stop and report"]
And if a stage fails *three* times, the run stops and reports.

# 2:30 Verdict (85%): the numbers

[SCREEN: manifest.json scrolled to the stages: seconds, vram_peak_mib, attempts | show=file | path=runs/2026-11-16_test/manifest.json | find="previous_passes">"stages" | skip=7 | n=18 | mark="vram_peak_mib": 902,"vram_peak_mib": 2390]
The manifest holds every number. Here is the *verdict*.

[EXPLAIN: scorecard row: software cost and electricity cost, values from the manifest | metrics=software,electricity | hook_source]
Software: *{$0|zero dollars}*. Electricity: about {0.1¢|zero point one cents}.

[EXPLAIN: stopwatch stopping at the total time from the manifest | metrics=wall | hook_source]
Script to MP4: *{2 min 41 s|two minutes and forty-one seconds}* on this laptop.

[EXPLAIN: memory bar with the peak GPU memory from the manifest, out of 8 GB | metrics=vram_peak | scene3d=GpuMemory3D]
Peak video memory: *{2.3 GB|two point three gigabytes}* out of eight.

[EXPLAIN: limits list: "placeholder screens", "generic voice", "no thumbnail yet"]
The *limits*: no real screen footage yet, and a generic voice.

# 2:50 Next

[SCREEN: the five-agent diagram again, the Writer box lit | show=terminal | capture=assets/screens/agents_readme.txt | mark=writer]
Next, the *Writer* agent: from idea to script, with sources.

[EXPLAIN: end card "Next: the Writer agent · The Build Log"]
That one is next, on The Build Log.

# Metadata

**Title:** This Video Made Itself: Script to MP4 for $0 on an 8GB GPU

**Description:**

A script goes in, a finished 1080p video comes out, and no one opens a video editor. We tested the Producer agent of The Build Log on an 8 GB laptop GPU: Kokoro-82M for the voice, faster-whisper large-v3-turbo for word timing, explainroo for diagrams, and FFmpeg for assembly. Every run writes a manifest with models, timings, video memory and cost.

0:00 The result
0:10 What goes in, what comes out
0:24 The voice: Kokoro
0:45 Why Whisper's numbers broke our subtitles
1:07 How the picture is built
1:43 Where the files live
1:56 The failure: FFmpeg "missing"
2:30 Verdict: cost, time, memory
2:50 Next: the Writer agent

Tools (all free and open source): Kokoro-82M, faster-whisper, explainroo, FFmpeg.

**Thumbnail ideas (max 3 words):**
1. "$0 VIDEO": the final video frame on the left, a huge orange "$0" on the right.
2. "NO EDITOR": a terminal with every line OK, crossed-out timeline-editor icon.
3. "SCRIPT → MP4": a text file and a play button linked by one blue arrow.

**Claims to verify after the production run (phase 4):**

| Claim | Status | Source |
| --- | --- | --- |
| $0 software | Measured | Everything is free/open source |
| 8 GB GPU, never above 3 GB | Measured in smoke test; confirm with manifest | nvidia-smi |
| Kokoro >4x real time, <1 GB | Measured: 7.85 s of speech in 1.8 s, 0.9 GB | smoke test 2026-11-16 |
| Whisper writes "twelve" as "12" | Observed | smoke test 2026-11-16 |
| Doctor reported FFmpeg missing; a refreshed PATH found it | Observed | doctor runs 2026-11-16 |
| 17 checks, 0 failures (16 OK, 1 WARN: no .env) | Observed | doctor run 2026-11-16 |
| Script to MP4: 2 min 41 s | Measured: cold pass 22 (am_echo 1.05x, gap 0.35 s), wall 161.23 s | runs/2026-11-16_test manifest.json (reference_metrics) |
| Electricity ≈ 0.1 cents | Estimated from measurement: 140 W × total stage time × USD 0.22/kWh = USD 0.0013 (pass 22) | manifest costs |
| Peak VRAM 2.3 GB | Measured: 2390 MiB in pass 22 (align stage) | manifest summary |
| Kokoro <1 GB in the pipeline | Measured: 902 MiB in pass 1 (tts stage) | manifest stages.tts |
| 1080p, 30 fps | Config; confirm with ffprobe | final.mp4 |

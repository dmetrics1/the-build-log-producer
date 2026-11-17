"""The Build Log Producer: approved script -> final.mp4 + manifest.json.

Stages: scenes (parser) -> tts (Kokoro) -> align (faster-whisper) ->
explain (explainroo) + SCREEN panels -> assemble (FFmpeg).
"""
__version__ = "0.1.0"

"""
Tools for working with subtitle-only workflows (no audio transcription).

This package provides a lightweight wrapper around the existing
`youtube_transcriber` helpers, focused on:

- Downloading native YouTube subtitles (without downloading audio/video)
- Optionally translating those subtitles (e.g. to Chinese)

All heavy audio / Whisper logic remains in `youtube_transcriber.py`.
"""


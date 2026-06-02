# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Running the Application

```bash
# Start the desktop GUI (also launches the Flask API server on port 8765)
python main.py

# Douyin command-line tool
python douyin_cli.py <抖音视频URL>
```

## Architecture Overview

### Entry Point & GUI (`main.py`)
The entire GUI is a single large file (~7400+ lines). Key classes:

- **`MainWindow(QMainWindow)`** — top-level window, owns all tab pages and application state. Tab pages are created by individual `create_*_tab()` methods.
- **`WorkerThread(QThread)`** — single background worker that handles all processing tasks (YouTube, Douyin, Twitter, Bilibili, local files, batch). Task type is set via `task_type` string. Always communicates results back to the UI via Qt signals.
- **Platform-specific QThread subclasses** — `DouyinParseThread`, `DouyinDownloadThread`, `DouyinBatchDownloadThread`, `LiveRecordingThread`, `GetLanguagesThread`, `DownloadSubtitleThread`, `SubtitleTranslateThread`.
- **Smart input widgets** — `URLLineEdit`, `DouyinLineEdit`, `URLTextEdit`, `DouyinTextEdit` override `contextMenuEvent` and `keyPressEvent` to provide platform-aware smart paste (auto-extracts URLs from Douyin share text, etc.).

### Core Processing (`youtube_transcriber.py`)
Houses the actual download/transcribe/translate/summarize logic as standalone functions. `main.py` calls these functions from within `WorkerThread`. All output directories are provided by `paths_config.py`.

### Output Directory Layout (`paths_config.py`)
All runtime-generated files go under `workspace/`:
```
workspace/
  videos/              # YouTube, Twitter, Bilibili video files
  downloads/           # audio-only files (.mp3)
  subtitles/           # generated subtitle files (.srt/.vtt/.ass)
  transcripts/         # raw transcript text
  summaries/           # LLM-generated markdown articles
  videos_with_subtitles/
  native_subtitles/    # subtitles downloaded directly from platform
  douyin_downloads/
  twitter_downloads/
  bilibili_downloads/
  live_downloads/
```

### Douyin Module (`douyin/`)
Self-contained package with `DouyinDownloader`, `DouyinConfig`, `DouyinUtils`, `DouyinVdExtractor`. Imported conditionally in `main.py`; `DOUYIN_AVAILABLE` flag guards all Douyin UI logic.

### Idle Queue System
Tasks are stored in `idle_queue.json` (project root). `MainWindow` runs a `QTimer` that calls `check_idle_time()` periodically. When the current time falls within the configured idle window (default 23:00–07:00), `execute_next_idle_task()` dequeues and runs the next task via `WorkerThread`.

### Chrome Extension ↔ Desktop Communication (`api_server.py`)
`APIServer` wraps a Flask app running in a daemon thread (port 8765). It exposes:
- `GET /api/health`
- `GET /api/queue` — list idle queue
- `POST /api/queue/add` — add task (called by Chrome extension)
- `DELETE /api/queue/clear`
- `DELETE /api/queue/remove/<task_id>`
- `GET/PUT /api/settings`

The server is started in `MainWindow.init_api_server()` after the GUI is shown.

### Live Recording (`live_recorder_adapter.py`)
Requires a `live_recorder/` directory at the project root (currently absent — only `live_recorder_backup/` exists). When the import fails, `LIVE_RECORDER_AVAILABLE = False` and the live recording tab still appears in the UI but cannot start recording. The live_recorder module is based on the DouyinLiveRecorder open-source project.

### Notification Pushes (`msg_push.py`)
Standalone module with functions for DingTalk, PushPlus, Bark, and email notifications. Called by the live recorder after recording events.

## Known Incomplete Areas

- **Live recording is non-functional**: `live_recorder/` directory is missing (only `live_recorder_backup/` exists). Renaming the backup to `live_recorder/` should restore the feature.
- **快手 / 虎牙 live detection** (`live_recorder_adapter.py:272–277`): detection logic is `pass`-only.
- **`douyin/downloader.py` `download_user_videos()`**: explicitly returns an error — batch user-profile download is not implemented.
- **`no_whisper_version/` removed**: the legacy full-code backup was deleted during path cleanup; active code lives under `src/` and `main.py`.

## Key Conventions

- All feature flags follow the pattern `FOO_AVAILABLE = True/False` set at import time, with the UI checking the flag before enabling the relevant widget.
- Background tasks must use `QThread` subclasses and communicate with the main thread exclusively through Qt signals — never touch PyQt6 widgets directly from a worker thread.
- New output directories should be added to `paths_config.py` using `_ensure_subdir()` and registered in `DIRECTORY_MAP` so the cleanup tab can discover them.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

# VideoHub

English | [简体中文](./README_cn.md)

VideoHub is a desktop video workflow application built with **PyQt6**. It combines **multi-platform downloading**, **speech transcription**, **bilingual subtitle generation**, **LLM summaries**, **idle-time queue scheduling**, **browser extension integration**, and **live recording utilities** in a single tool.

It is designed for users who want to turn online videos into reusable assets: local video/audio files, transcripts, subtitles, and structured markdown summaries.

## Feature Overview

| Feature | Description |
| --- | --- |
| Multi-platform download | Download content from YouTube, Twitter/X, Douyin, Bilibili, Koushare, and more. |
| Audio / video workflows | Save full video or audio-only output depending on the task. |
| Whisper transcription | Transcribe local or online media using OpenAI Whisper. |
| Bilingual subtitles | Generate `.srt`, `.vtt`, and `.ass` subtitles, with optional translation. |
| Subtitle burn-in | Embed subtitles into video files when the workflow requires it. |
| LLM summaries | Generate markdown summaries/articles from transcripts with customizable templates. |
| Batch processing | Process multiple URLs or local files in one run. |
| Idle queue scheduling | Queue tasks during the day and let VideoHub execute them in a configured idle window. |
| Browser extension | Add supported video pages directly to the local queue from Chrome/Edge. |
| Live recording | Includes a live recording integration layer for monitored stream capture. |
| FFmpeg management | Built-in FFmpeg configuration and testing helpers. |

## Current Limitations

- The live recording feature is currently **not fully functional** if the project root does not contain `live_recorder/`.
- `src/douyin/downloader.py` still reports that **Douyin user-profile batch download is not implemented**.
- Some live platform detection branches in `src/live_recorder_adapter.py` are incomplete.
- Parts of the application are still centered around a large single-file GUI controller in `main.py`.

## Quick Start

### 1. Requirements

- Python 3.8+
- Windows is the primary tested platform
- FFmpeg for subtitle/video processing and live recording
- Optional: Chrome/Edge for the browser extension
- Optional: CUDA-capable GPU for faster Whisper transcription

### 2. Clone and install

```bash
git clone git@github.com:cacity/VideoHub.git
cd VideoHub

# Optional but recommended
conda create -n VideoHub python=3.12
conda activate VideoHub

pip install -r requirements.txt
```

### 3. Start the desktop app

```bash
python main.py
```

This launches the PyQt desktop GUI and also starts the local Flask API server on port `8765` for queue integration.

### 4. Optional command-line entry points

```bash
python src/youtube_transcriber.py --help
python src/douyin_cli.py "https://v.douyin.com/xxxxx/"
python src/ffmpeg_config_cli.py help
```

## Minimal Working Configuration

Create a `.env` file in the project root if you want summary generation or custom API endpoints.

```env
OPENAI_API_KEY=your_openai_key
OPENAI_BASE_URL=
OPENAI_MODEL=
DEEPSEEK_API_KEY=
KOUSHARE_ACCESS_TOKEN=
```

You can also configure many options from the GUI settings page instead of editing `.env` manually.

## Usage

### Desktop GUI

Run the main application:

```bash
python main.py
```

Main tabs in the GUI include:

- **Online Video**
- **Local Audio / Video**
- **Batch Processing**
- **Idle Queue**
- **Live Recorder**
- **Download History**
- **Settings**

### Media processing CLI

`src/youtube_transcriber.py` is the main reusable CLI for transcription, subtitles, summaries, template management, batch jobs, and cleanup.

#### Common examples

```bash
# Process a single YouTube video
python src/youtube_transcriber.py --youtube "https://www.youtube.com/watch?v=VIDEO_ID"

# Download video and generate subtitles
python src/youtube_transcriber.py --youtube "https://www.youtube.com/watch?v=VIDEO_ID" --download-video --generate-subtitles

# Burn subtitles into the downloaded/local video
python src/youtube_transcriber.py --youtube "https://www.youtube.com/watch?v=VIDEO_ID" --download-video --generate-subtitles --embed-subtitles

# Process a local audio file
python src/youtube_transcriber.py --audio "path/to/file.mp3"

# Process a local video file
python src/youtube_transcriber.py --video "path/to/file.mp4" --generate-subtitles

# Generate a summary directly from text
python src/youtube_transcriber.py --text "path/to/file.txt"

# Process multiple URLs
python src/youtube_transcriber.py --urls "<url1>" "<url2>"

# Preview cleanup
python src/youtube_transcriber.py --cleanup-preview
```

#### Key arguments

| Argument | Description |
| --- | --- |
| `--youtube` | Process a single YouTube URL |
| `--audio` | Process a local audio file |
| `--video` | Process a local video file |
| `--text` | Generate a summary from a local text file |
| `--batch` | Read URLs from a text file |
| `--urls` | Process multiple URLs from the command line |
| `--download-video` | Save full video instead of audio-only |
| `--generate-subtitles` | Generate subtitle files |
| `--no-translate` | Skip subtitle translation |
| `--embed-subtitles` | Burn subtitles into the video |
| `--transcribe-only` | Skip summary generation |
| `--template` | Use a named or explicit template file |
| `--history` | Show download/processing history |
| `--cleanup` | Clean generated output directories |

## Douyin Download

For Douyin single-video download, use the dedicated CLI:

```bash
python src/douyin_cli.py "https://v.douyin.com/xxxxx/"
python src/douyin_cli.py "https://www.douyin.com/video/xxxxx" -o "workspace/douyin_downloads"
```

Notes:

- It is designed for **single video download**.
- It expects the required Douyin backend/service to be available.
- User-profile batch download is not implemented in the current backend.

## Koushare Support

VideoHub includes dedicated Koushare support.

Current behavior:

- Login/token logic lives in the GUI and in `src/koushare_downloader.py`
- `Authorization` uses the raw token value, **not** `Bearer <token>`
- Higher-quality playback (such as FHD) may require a valid login token

Recommended usage:

- Open the desktop app
- Go to the settings tab
- Log in with your Koushare account or paste an existing token
- Then process the target Koushare URL through the standard workflow

## Browser Extension

The `chrome_extension/` folder contains the local browser extension.

Typical flow:

1. Load the unpacked extension in Chrome/Edge
2. Start `python main.py`
3. Open a supported video page
4. Click the injected button to add the task into the local idle queue

The extension communicates with the desktop app through the local API server.

## Idle Queue API

Once the GUI is running, the local API is available on `http://127.0.0.1:8765`.

### Available endpoints

- `GET /api/health`
- `GET /api/queue`
- `POST /api/queue/add`
- `DELETE /api/queue/clear`
- `DELETE /api/queue/remove/<task_id>`
- `GET /api/settings`
- `PUT /api/settings`

### Example calls

```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/queue
curl -X POST http://127.0.0.1:8765/api/queue/add -H "Content-Type: application/json" -d '{"platform":"youtube","url":"https://example.com","title":"sample"}'
```

Required fields for queue insertion:

- `platform`
- `url`
- `title`

## FFmpeg Management

VideoHub ships with an FFmpeg management CLI:

```bash
python src/ffmpeg_config_cli.py status
python src/ffmpeg_config_cli.py test
python src/ffmpeg_config_cli.py mode auto
python src/ffmpeg_config_cli.py path "C:/ffmpeg/bin/ffmpeg.exe"
python src/ffmpeg_config_cli.py download
```

Use it to inspect current FFmpeg status, switch execution modes, set a custom binary path, or download FFmpeg.

## Output Structure

Runtime-generated files are placed under `workspace/`.

```text
workspace/
  videos/
  downloads/
  subtitles/
  transcripts/
  summaries/
  videos_with_subtitles/
  native_subtitles/
  douyin_downloads/
  twitter_downloads/
  bilibili_downloads/
  live_downloads/
```

## Project Structure

```text
VideoHub/
├── main.py
├── src/
│   ├── youtube_transcriber.py
│   ├── douyin_cli.py
│   ├── ffmpeg_config_cli.py
│   ├── api_server.py
│   ├── koushare_downloader.py
│   ├── live_recorder_adapter.py
│   └── subtitle_merger.py
├── chrome_extension/
├── workspace/
├── templates/
├── logs/
├── idle_queue.json
└── README.md
```

## Supported Platforms

| Platform | Download | Transcription | Subtitles | Notes |
| --- | --- | --- | --- | --- |
| YouTube | Yes | Yes | Yes | Native subtitle extraction available in some cases |
| Twitter / X | Yes | Yes | Yes | Login/cookies may help on restricted content |
| Douyin | Yes | Yes | Yes | Single-video workflow is the main supported path |
| Bilibili | Yes | Yes | Yes | Uses the shared media-processing pipeline |
| Koushare | Yes | Yes | Yes | Login token may be required for higher quality |

## Typical Scenarios

### Scenario 1: Download a YouTube course playlist and generate subtitles

- Paste the playlist/video URL into the GUI
- Enable subtitle generation
- Optionally translate subtitles
- Save outputs under `workspace/`

### Scenario 2: Queue tasks during the day and process them at night

- Start `python main.py`
- Add items from the GUI or browser extension
- Let the idle queue run during the configured time window

### Scenario 3: Download a Douyin video without watermark

- Copy the Douyin link or share text
- Extract the URL if needed
- Run `python src/douyin_cli.py "<douyin-url>"`

### Scenario 4: Turn a local lecture recording into a markdown summary

- Run `python src/youtube_transcriber.py --video "path/to/file.mp4"`
- Configure API keys if you want LLM summary generation
- Review transcript, subtitles, and summary in `workspace/`

## Testing

There is no unified automated test suite documented in the repository yet. For smoke testing, use the existing entry points:

```bash
python src/youtube_transcriber.py --help
python src/douyin_cli.py --help
python src/ffmpeg_config_cli.py help
python main.py
```

## License

This project is licensed under the [MIT License](./LICENSE).

## Acknowledgements

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [OpenAI Whisper](https://github.com/openai/whisper)
- [Flask](https://flask.palletsprojects.com/)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=cacity/VideoHub&type=Date)](https://www.star-history.com/#cacity/VideoHub&Date)

If this project helps you, a star is welcome.
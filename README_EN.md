# Video Transcription Tool (Video Hub) 🎬

This is a powerful desktop application built with PyQt6, featuring a modern graphical interface that supports intelligent processing of video content from multiple platforms including **YouTube, Twitter/X, Douyin, Bilibili**. It provides a complete workflow including video download, speech transcription, bilingual subtitle generation, content summarization, and advanced features like idle-time scheduling and batch processing.

## 🌟 Project Highlights

- 🎯 **All-in-One Solution** - Integrates video download, transcription, translation, and summarization
- 🌐 **Multi-Platform Support** - YouTube, Twitter/X, Douyin, Bilibili, and other mainstream platforms
- 🤖 **AI-Driven** - Powered by OpenAI Whisper (transcription) + GPT/DeepSeek (summarization)
- 🎨 **Modern GUI** - Beautiful and user-friendly interface based on PyQt6
- 🔧 **Smart Tool Management** - Automatic dual-version management for FFmpeg and yt-dlp
- 🌐 **Browser Integration** - Chrome extension for one-click queue addition
- 📺 **Live Stream Recording** - Multi-platform live stream monitoring and automatic recording
- ⏰ **Idle-Time Scheduling** - Intelligent task queue utilizing off-peak resources
- 🚀 **Highly Configurable** - Rich configuration options to meet different needs

## ✨ Core Features

### 🎬 Multi-Platform Video Processing
- **🎥 Platform Support**: YouTube, Twitter/X, Douyin, Bilibili, and other mainstream video platforms
- **Smart Download**: Support for video/audio download with options for full video or audio-only mode
- **Accurate Transcription**: High-quality speech transcription powered by OpenAI Whisper
- **Multi-Format Subtitles**: Generate bilingual subtitles in .srt, .vtt, .ass, and other formats
- **Subtitle Embedding**: Support for embedding subtitles directly into video files
- **Content Summarization**: Intelligent article generation using LLMs (supports OpenAI, DeepSeek, etc.)

### 📺 Live Stream Recording Features
- **Multi-Platform Monitoring**: Supports Douyin, Kuaishou, Huya, Douyu, Bilibili, TikTok, and other live streaming platforms
- **Automatic Recording**: Real-time stream monitoring, auto-start recording when live, auto-stop when offline
- **HD Recording**: Support for multiple quality options including original, ultra-clear, and high-definition
- **Multi-Format Output**: Support for TS, FLV, MP4, and other video formats
- **Batch Monitoring**: Monitor multiple live rooms simultaneously with automatic task management
- **Message Push**: Support for DingTalk, PushPlus, email, and other notification methods
- **Scheduled Detection**: Configurable monitoring intervals to balance performance and real-time responsiveness

### 🌐 Chrome Browser Extension
- **Page Integration**: Automatically add download buttons on YouTube, Twitter/X, and Bilibili video pages
- **One-Click Queue Addition**: Click buttons to add videos to idle-time download queue
- **Queue Management**: View, export, and clear download queue through extension popup
- **Real-Time Sync**: Real-time communication with desktop app via HTTP API
- **Smart Recognition**: Automatically extract video title, author, link, and other information
- **Visual Feedback**: Button state changes after successful addition to avoid duplicates

### 🔄 Batch Processing
- **Multi-Platform Batch Processing**: Support for mixed processing of video links from different platforms
- **File Import**: Bulk import URL lists from text files
- **Progress Tracking**: Real-time display of batch task processing progress and results

### ⏰ Idle-Time Scheduling System
- **Smart Scheduling**: Set idle-time periods (e.g., 11:00 PM - 7:00 AM) for automatic download task execution
- **Task Queue**: Add tasks to queue during daytime, automatically execute sequentially during idle time
- **Flexible Control**: Support for pause/resume, immediate execution, task reordering, and other operations
- **Visual Management**: Dedicated "Idle Queue" tab for real-time task status viewing and management

### ⚙️ FFmpeg & yt-dlp Dual Version Management 🆕
- **Flexible Switching**: Support for both Python library and executable file methods
- **Auto Configuration**: Automatic path configuration and mode setup after download
- **Three Modes**:
  - **Python Library Mode**: Use pip-installed libraries (developer-friendly)
  - **Executable File Mode**: Use standalone .exe files (no dependencies)
  - **Auto Mode**: Intelligently select available method (recommended)
- **One-Click Download**:
  - FFmpeg: Support for 3 backup download sources (Gyan.dev/GitHub/LanzouCloud)
  - yt-dlp: Automatic download from official GitHub source
- **GUI Configuration**: Visual configuration in settings page, support for browsing local files
- **Path Management**: Auto-detect system installation or specify custom path
- **Real-Time Testing**: One-click test to verify functionality

### 🛠️ Convenient Tools
- **Smart Paste**: URL input box supports right-click paste, auto-recognizes YouTube, Twitter, X, Douyin, and other platform links
- **Douyin Share Support**: Intelligently recognize Douyin shared content, auto-extract video links
- **Task Interruption**: Support for interrupting long-running tasks
- **Download History**: Complete processing history and file management
- **Template System**: Custom article generation templates for personalized output formats

### 🎯 Multi-Scenario Support
- **Online Videos**: Complete processing workflow for YouTube, Twitter/X, Douyin, Bilibili, and other platform videos
- **Local Files**: Support for transcription and processing of local audio and video files
- **Plain Text Processing**: LLM summarization and organization of existing text
- **Cookie Support**: Process restricted video content requiring login

## 🖼️ Application Interface

### Main Interface Tabs
- **Online Video**: Single video processing, supports YouTube, Twitter, X, Douyin, and multiple platforms
- **Local Audio**: Process local audio files
- **Local Video**: Process local video files
- **Local Text**: Process plain text content
- **Batch Processing**: Batch process multiple video links from different platforms
- **Idle Queue**: Visual task queue management and idle-time scheduling control
- **Download History**: View all processed video records
- **Subtitle Translation**: Subtitle file translation tool
- **Live Recording**: Multi-platform live stream monitoring and automatic recording management
- **Cleanup Tools**: Clean temporary files and cache
- **Settings**: API configuration, FFmpeg/yt-dlp configuration, template management, idle-time settings

## 🚀 Quick Start

### 📋 System Requirements

**Required**:
- Python 3.8+ (Python 3.10-3.12 recommended)
- Windows/macOS/Linux operating system
- 4GB+ available disk space (for models and video cache)
- Stable internet connection

**Recommended**:
- 8GB+ RAM (for Whisper model execution)
- NVIDIA GPU + CUDA (accelerate Whisper transcription, optional)
- Chrome browser (when using browser extension)
- Proxy server (when accessing restricted platforms)

### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/your-repo/VideoHub.git
cd VideoHub

# Create virtual environment (recommended)
conda create -n VideoHub python=3.12
conda activate VideoHub

# Install dependencies
pip install -r requirements.txt
```

### Core Dependencies
```txt
PyQt6                    # Modern GUI framework
yt-dlp                   # Multi-platform video download
openai-whisper           # Speech transcription
openai                   # OpenAI API
ffmpeg-python            # FFmpeg Python library (optional)
requests                 # HTTP requests
python-dotenv            # Environment variable management
flask                    # API server
flask-cors               # CORS support
```

### 2. Configure FFmpeg and yt-dlp 🆕

**Choose one of two methods:**

#### Method 1: Configure in Program GUI (Recommended) ⭐

1. Run the program: `python main.py`
2. Go to "Settings" tab
3. Find "FFmpeg Settings" and "yt-dlp Settings" sections

**FFmpeg Configuration**:
- Mode selection: "Auto" (recommended)
- Check "Auto-download if not found"
- Click "Download FFmpeg" button (Windows users)
- Or click "Browse" to specify local ffmpeg.exe
- Click "Test FFmpeg" to verify
- Click "Save Settings" at the bottom

**yt-dlp Configuration**:
- Mode selection: "Auto" (recommended)
- Check "Auto-download if not found"
- Click "Download yt-dlp" button
- Or click "Browse" to specify local yt-dlp
- Click "Test yt-dlp" to verify
- Click "Save Settings" at the bottom

#### Method 2: Use Command Line Tool

```bash
# FFmpeg configuration
python ffmpeg_config_cli.py status      # Check status
python ffmpeg_config_cli.py download    # Download FFmpeg
python ffmpeg_config_cli.py test        # Test

# yt-dlp configuration
# (yt-dlp is usually auto-installed with pip install yt-dlp)
```

#### Method 3: Manual Installation

**FFmpeg**:
- Windows: Visit https://www.gyan.dev/ffmpeg/builds/ to download
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg` or `sudo yum install ffmpeg`

**yt-dlp**:
```bash
pip install yt-dlp
```

**Detailed Documentation**:
- FFmpeg Configuration: [FFMPEG_README.md](FFMPEG_README.md)
- yt-dlp Configuration: [YTDLP_SETUP.md](YTDLP_SETUP.md)
- Dual Tool Configuration: [DUAL_VERSION_SETUP.md](DUAL_VERSION_SETUP.md)
- Download Troubleshooting: [FFMPEG_DOWNLOAD_TROUBLESHOOTING.md](FFMPEG_DOWNLOAD_TROUBLESHOOTING.md)

### 3. Configure API Keys

Configure in the application's "Settings" tab:

```env
# OpenAI API (for GPT models and Whisper)
OPENAI_API_KEY=sk-your-openai-api-key

# DeepSeek API (domestic alternative)
DEEPSEEK_API_KEY=your-deepseek-api-key

# Proxy settings (if needed)
PROXY=http://127.0.0.1:7890
```

### 4. Install Chrome Browser Extension (Optional)

1. Open Chrome browser, visit `chrome://extensions/`
2. Enable "Developer mode" in the top right corner
3. Click "Load unpacked"
4. Select the `chrome_extension` folder in the project
5. The extension will appear in the extensions list

### 5. Run Application

```bash
# Start desktop application
python main.py

# Or use Douyin command-line tool
python douyin_cli.py <Douyin video URL>

# Or use standalone API server
python api_server.py
```

## 📖 Usage Guide

### 🎬 Process Single Video

1. **Copy Video Link**
   - YouTube: `https://www.youtube.com/watch?v=xxxxx` or `https://youtu.be/xxxxx`
   - Twitter/X: `https://x.com/user/status/xxxxx` or `https://twitter.com/user/status/xxxxx`
   - Douyin: In app, click Share → Copy Link (supports auto-recognition of shared text)
   - Bilibili: `https://www.bilibili.com/video/BVxxxxxxxxxx`

2. **Paste into Program**
   - Right-click paste in the "Video URL" input box on the "Online Video" tab
   - The program will automatically recognize and extract the correct video link

3. **Select Processing Options**
   - ☑ **Download Video** - Download complete video file (highest available quality)
   - ☑ **Download Audio** - Download audio track only (save time and space)
   - ☑ **Extract Subtitles** - Use Whisper for speech transcription
   - ☑ **Translate Subtitles** - Translate subtitles to target language
   - ☑ **Generate Summary** - Use LLM to generate content summary

4. **Start Processing**
   - Click "Start Processing" button
   - View real-time processing progress and detailed logs
   - Support for interrupting tasks at any time

### Batch Processing

1. Go to "Batch Processing" tab
2. Paste multiple video links in text box (one per line)
3. Supports mixing links from different platforms
4. Click "Start Batch Processing"

### Idle Queue

1. Set idle time (e.g., 11:00 PM - 7:00 AM)
2. Use Chrome extension or program to add tasks to queue
3. Program will automatically process queue tasks during idle time

### Live Recording

1. Go to "Live Recording" tab
2. Configure `live_config/URL_config.ini` to add live rooms
3. Click "Start Monitoring"
4. Auto-record when streamer goes live

## 📂 Project Structure

```
VideoHub/
├── 📁 Core Files
│   ├── main.py                        # PyQt6 GUI main program
│   ├── api_server.py                  # HTTP API server
│   ├── youtube_transcriber.py         # YouTube transcription core
│   ├── douyin_cli.py                  # Douyin command-line tool
│   ├── live_recorder_adapter.py       # Live recording adapter
│   ├── msg_push.py                    # Message push module
│   └── requirements.txt               # Python dependencies
│
├── 📁 FFmpeg & yt-dlp Management 🆕
│   ├── ffmpeg_manager.py              # FFmpeg manager
│   ├── ffmpeg_config.json             # FFmpeg configuration
│   ├── ffmpeg_install.py              # FFmpeg installation script
│   ├── ffmpeg_config_cli.py           # FFmpeg CLI tool
│   ├── ytdlp_manager.py               # yt-dlp manager
│   ├── ytdlp_config.json              # yt-dlp configuration
│   ├── ffmpeg_setup.bat/.sh           # Configuration scripts
│   ├── test_ffmpeg_download.py        # Download test
│   └── diagnose_ffmpeg_download.py    # Diagnostic tool
│
├── 📁 Chrome Extension
│   └── chrome_extension/
│       ├── manifest.json              # Extension configuration
│       ├── background.js              # Background service
│       ├── content-scripts/           # Page scripts
│       │   ├── youtube.js
│       │   ├── twitter.js
│       │   ├── bilibili.js
│       │   └── styles.css
│       └── popup/                     # Extension popup
│           ├── popup.html
│           ├── popup.js
│           └── popup.css
│
├── 📁 Douyin Download Module
│   └── douyin/
│       ├── parser.py                  # URL parsing
│       ├── downloader.py              # Video download
│       ├── video_extractor.py         # Video extraction
│       ├── douyinvd_extractor.py      # DouyinVD extractor
│       ├── dlpanda_extractor.py       # DLPanda extractor
│       ├── selenium_extractor.py      # Selenium extractor
│       ├── smart_selenium_extractor.py # Smart Selenium extractor
│       ├── ytdlp_wrapper.py           # yt-dlp wrapper
│       ├── advanced_signer.py         # Advanced signing
│       ├── config.py                  # Configuration file
│       └── utils.py                   # Utility functions
│
├── 📁 Live Recording Module
│   ├── live_recorder/
│   │   ├── spider.py                  # Live streaming spider
│   │   ├── stream.py                  # Stream processing
│   │   ├── room.py                    # Live room management
│   │   └── ...
│   └── live_config/
│       ├── config.ini                 # Recording configuration
│       └── URL_config.ini             # Live room list
│
├── 📁 Output Directories
│   ├── downloads/                     # Downloaded audio files
│   ├── videos/                        # Downloaded video files
│   ├── douyin_downloads/              # Douyin videos (if exists)
│   ├── ffmpeg/                        # FFmpeg executable directory 🆕
│   ├── ytdlp/                         # yt-dlp executable directory 🆕
│   ├── transcripts/                   # Transcription texts
│   ├── subtitles/                     # Subtitle files
│   ├── summaries/                     # LLM-generated article summaries
│   └── logs/                          # Program runtime logs
│
├── 📁 Configuration Files
│   ├── .env                           # Environment variables (API keys, etc.)
│   ├── ffmpeg_config.json             # FFmpeg configuration 🆕
│   ├── ytdlp_config.json              # yt-dlp configuration 🆕
│   ├── idle_queue.json                # Idle queue data
│   └── templates/                     # Article generation templates
│
└── 📁 Utility Scripts
    ├── ffmpeg_setup.bat/.sh           # FFmpeg quick setup script
    ├── diagnose_ffmpeg_download.py    # Download diagnostic tool 🆕
    ├── test_ffmpeg_download.py        # Download test script 🆕
    ├── cleanup_test_files.py          # Cleanup test files
    ├── copy_project.py                # Project copy tool
    └── 带时间戳Tag.bat                 # Batch processing tool
```

## 🔧 Troubleshooting

### FFmpeg/yt-dlp Download Failed

1. **Run diagnostic tool**:
   ```bash
   python diagnose_ffmpeg_download.py
   ```

2. **Check detailed logs**:
   - View console output while program is running
   - Identify specific error messages

3. **Use manual download**:
   - Refer to [FFMPEG_MANUAL_DOWNLOAD.md](FFMPEG_MANUAL_DOWNLOAD.md)
   - After download, use "Browse" button to specify path

4. **Set proxy** (if needed):
   ```bash
   # Windows
   set HTTP_PROXY=http://127.0.0.1:7890
   set HTTPS_PROXY=http://127.0.0.1:7890
   
   # Linux/Mac
   export HTTP_PROXY=http://127.0.0.1:7890
   export HTTPS_PROXY=http://127.0.0.1:7890
   ```

### Video Download Failed

- Check network connection
- Verify video link is valid
- Update yt-dlp: `pip install --upgrade yt-dlp`
- Check program logs for detailed errors

### Whisper Transcription Slow

- First run will download model (~1.5GB)
- GPU acceleration recommended (requires CUDA version of PyTorch)
- Choose smaller models (tiny, base, small)
- For long videos, download audio only to speed up processing

### Chrome Extension Cannot Connect

- Ensure API server is running (`python api_server.py` or main program started)
- Check if firewall is blocking port 5000
- Check connection status and error messages in extension popup
- Ensure extension is properly loaded (check chrome://extensions)

## 📝 Changelog

### v2.0.0 - 2024-11-05 🆕

**Major Updates**:
- ✅ New FFmpeg and yt-dlp dual version management system
- ✅ Support for both Python library and executable file modes (auto/manual switching)
- ✅ Visual configuration of FFmpeg and yt-dlp in settings interface
- ✅ One-click download and auto-configuration functionality
- ✅ Multiple download sources (3 FFmpeg sources, official GitHub yt-dlp source)
- ✅ Auto-fill path and save configuration after successful download
- ✅ New diagnostic tool and test scripts (`diagnose_ffmpeg_download.py`)
- ✅ Detailed download logs and error handling
- ✅ Comprehensive documentation system

**Improvements**:
- 🔧 Fixed FFmpeg download string concatenation error
- 🔧 Improved extraction logic, intelligently handle different archive structures
- 🔧 Enhanced error messages, provide detailed solutions
- 🔧 Optimized download speed (increased chunk size to 8KB)
- 🔧 Added download timeout and retry mechanism
- 🔧 Improved GUI configuration interface, support for real-time testing and validation

### v1.x.x - Previous Versions
- Basic video processing features
- Chrome extension
- Live recording
- Idle queue
- And more...

## 💡 Advanced Tips

### 🔐 Process Videos Requiring Login
Some platform videos require login to access, this can be solved by providing a Cookie file:
1. Export cookies using browser extension (e.g., "Get cookies.txt")
2. Specify cookie file path in settings
3. Cookies will be automatically used for authentication when processing videos

### ⚡ Optimize Processing Speed
- **Download Audio Only**: If only transcription is needed, skipping video download can save significant time
- **Choose Appropriate Whisper Model**:
  - `tiny/base`: Fast, lower accuracy, suitable for quick preview
  - `small/medium`: Balance speed and accuracy, recommended for daily use
  - `large`: Highest accuracy, but slower
- **Use GPU Acceleration**: Installing CUDA version of PyTorch can accelerate 5-10x
- **Batch Processing**: Process multiple videos together to fully utilize system resources

### 🎨 Custom Article Templates
Create custom template files in the `templates/` directory:
```
Title: {title}
Author: {author}
Duration: {duration}

【Content Summary】
{summary}

【Key Points】
{key_points}
```

### 🌐 Use Proxy
Configure proxy in `.env` file:
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

### 📊 Live Recording Best Practices
- **Monitoring Interval**: Recommended 30-60 seconds, balance real-time and server pressure
- **Quality Selection**: Choose appropriate quality based on network speed to avoid buffering
- **Storage Space**: Reserve sufficient disk space in advance, long streams can generate tens of GB
- **Multi-Platform Monitoring**: Monitor multiple live rooms simultaneously, but mind system resources

## 🛠️ Tech Stack

### Core Frameworks
- **PyQt6** - Cross-platform GUI framework
- **Flask** - HTTP API server
- **yt-dlp** - Multi-platform video download engine

### AI/ML
- **OpenAI Whisper** - Speech transcription model
- **PyTorch** - Deep learning framework
- **OpenAI API** - GPT model interface
- **DeepSeek API** - Domestic LLM alternative

### Video Processing
- **FFmpeg** - Audio/video processing tool
- **ffmpeg-python** - FFmpeg Python wrapper

### Web Scraping
- **Selenium** - Browser automation (Douyin download)
- **aiohttp/httpx** - Async HTTP client
- **BeautifulSoup4** - HTML parsing
- **requests** - HTTP request library

### Other Tools
- **python-dotenv** - Environment variable management
- **loguru** - Logging system
- **tqdm** - Progress bar display

## 🤝 Contributing

Issues and Pull Requests are welcome!

If you have good ideas or found bugs, please:
1. Search GitHub Issues for related problems
2. Provide detailed reproduction steps and environment information
3. If possible, attach log files and screenshots

**Contribution Types**:
- 🐛 Bug fixes
- ✨ New feature development
- 📝 Documentation improvements
- 🌐 New platform support
- 🎨 UI/UX optimization
- 🔧 Performance optimization

## 📄 License

MIT License

## 💬 Contact

- GitHub: [VideoHub](https://github.com/cacity/VideoHub)
- Issues: [Report Bug](https://github.com/cacity/VideoHub/issues)

---

**Tip**: Don't forget to click the "Save Settings" button after configuration! 🎉

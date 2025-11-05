# 视频转录工具 (Video Hub) 🎬

这是一个功能强大的桌面应用程序，使用 PyQt6 构建现代化图形界面，支持 **YouTube、Twitter/X、抖音、Bilibili** 等多平台视频内容的智能处理。提供视频下载、语音转录、双语字幕生成、内容摘要等完整工作流，并配备闲时调度、批量处理等高级功能。英文版[README.md](./README_EN.md)

## 🌟 项目亮点

- 🎯 **一站式解决方案** - 集视频下载、转录、翻译、摘要于一体
- 🌐 **多平台支持** - YouTube、Twitter/X、抖音、Bilibili 等主流平台
- 🤖 **AI 驱动** - 集成 OpenAI Whisper（转录）+ GPT/DeepSeek（摘要）
- 🎨 **现代化 GUI** - 基于 PyQt6 的美观易用界面
- 🔧 **智能工具管理** - FFmpeg 和 yt-dlp 双版本自动管理
- 🌐 **浏览器集成** - Chrome 扩展实现一键添加到队列
- 📺 **直播录制** - 支持多平台直播监控和自动录制
- ⏰ **闲时调度** - 智能任务队列，充分利用闲时资源
- 🚀 **高度可配置** - 丰富的配置选项，满足不同需求

## ✨ 核心功能

### 🎬 多平台视频处理
- **🎥 平台支持**: YouTube、Twitter/X、抖音、Bilibili 等主流视频平台
- **智能下载**: 支持视频/音频下载，可选择完整视频或仅音频模式
- **精准转录**: 基于 OpenAI Whisper 的高质量语音转录技术
- **多格式字幕**: 生成 .srt、.vtt、.ass 等多种格式的双语字幕文件
- **字幕嵌入**: 支持将字幕直接嵌入到视频文件中
- **内容摘要**: 利用 LLM（支持 OpenAI、DeepSeek 等）智能生成文章摘要

### 📺 直播录制功能
- **多平台监控**: 支持抖音、快手、虎牙、斗鱼、B站、TikTok 等多个直播平台
- **自动录制**: 实时监控直播状态，开播自动录制，下播自动停止
- **高清录制**: 支持原画、超清、高清等多种画质选择
- **多格式输出**: 支持 TS、FLV、MP4 等多种视频格式
- **批量监控**: 可同时监控多个直播间，自动管理录制任务
- **消息推送**: 支持钉钉、PushPlus、邮件等多种开播提醒方式
- **定时检测**: 可配置监控间隔，平衡性能和实时性

### 🌐 Chrome浏览器扩展
- **页面集成**: 在 YouTube、Twitter/X、Bilibili 视频页面自动添加下载按钮
- **一键加入队列**: 点击按钮即可将视频添加到闲时下载队列
- **队列管理**: 通过扩展弹窗查看、导出、清空下载队列
- **实时同步**: 通过 HTTP API 与桌面应用实时通信
- **智能识别**: 自动提取视频标题、作者、链接等信息
- **视觉反馈**: 添加成功后按钮状态变化，避免重复添加

### 🔄 批量处理
- **多平台批处理**: 支持混合处理不同平台的视频链接
- **文件导入**: 可从文本文件批量导入 URL 列表
- **进度跟踪**: 实时显示批量任务的处理进度和结果

### ⏰ 闲时调度系统
- **智能调度**: 设置闲时时间段（如晚上23:00-早晨07:00），自动执行下载任务
- **任务队列**: 白天将任务添加到队列，闲时自动依次执行
- **灵活控制**: 支持暂停/恢复、立即执行、任务重排等操作
- **可视化管理**: 专门的"闲时队列"标签页，实时查看和管理任务状态

### ⚙️ FFmpeg & yt-dlp 双版本管理 🆕
- **灵活切换**: 支持 Python库 和 可执行文件 两种方式
- **自动配置**: 下载后自动配置路径和模式
- **三种模式**:
  - **Python库模式**: 使用 pip 安装的库（开发友好）
  - **可执行文件模式**: 使用独立的 .exe 文件（无依赖）
  - **自动模式**: 智能选择可用方式（推荐）
- **一键下载**:
  - FFmpeg: 支持3个备用下载源（Gyan.dev/GitHub/蓝奏云）
  - yt-dlp: 从GitHub官方源自动下载
- **GUI配置**: 在设置页面可视化配置，支持浏览本地文件
- **路径管理**: 自动检测系统安装或指定自定义路径
- **实时测试**: 一键测试功能是否正常工作

### 🛠️ 便捷工具
- **智能粘贴**: URL 输入框支持右键直接粘贴，自动识别 YouTube、Twitter、X、抖音等平台链接
- **抖音分享支持**: 智能识别抖音分享内容，自动提取视频链接
- **任务中断**: 支持中断正在执行的长时间任务
- **下载历史**: 完整的处理历史记录和文件管理
- **模板系统**: 自定义文章生成模板，个性化输出格式

### 🎯 多场景支持
- **在线视频**: YouTube、Twitter/X、抖音、Bilibili 等平台视频的完整处理流程
- **本地文件**: 支持本地音频、视频文件的转录和处理
- **纯文本处理**: 对已有文本进行 LLM 摘要和整理
- **Cookie 支持**: 处理需要登录的受限视频内容

## 🖼️ 应用界面

### 主界面标签页
- **在线视频**: 单个视频处理，支持 YouTube、Twitter、X、抖音等多平台
- **本地音频**: 处理本地音频文件
- **本地视频**: 处理本地视频文件
- **本地文本**: 处理纯文本内容
- **批量处理**: 批量处理多个不同平台的视频链接
- **闲时队列**: 可视化任务队列管理和闲时调度控制
- **下载历史**: 查看所有处理过的视频记录
- **字幕翻译**: 字幕文件翻译工具
- **直播录制**: 多平台直播监控和自动录制管理
- **清理工具**: 清理临时文件和缓存
- **设置**: API 配置、FFmpeg/yt-dlp 配置、模板管理、闲时设置

## 🚀 快速开始

### 📋 系统要求

**必需**：
- Python 3.8+ （推荐 Python 3.10-3.12）
- Windows/macOS/Linux 操作系统
- 4GB+ 可用磁盘空间（用于模型和视频缓存）
- 稳定的网络连接

**推荐**：
- 8GB+ RAM（用于 Whisper 模型运行）
- NVIDIA GPU + CUDA（加速 Whisper 转录，可选）
- Chrome浏览器（使用浏览器扩展时）
- 代理服务器（访问受限平台时）

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/your-repo/VideoHub.git
cd VideoHub

# 创建虚拟环境（推荐）
conda create -n VideoHub python=3.12
conda activate VideoHub

# 安装依赖
pip install -r requirements.txt
```

### 核心依赖
```txt
PyQt6                    # 现代化GUI框架
yt-dlp                   # 多平台视频下载
openai-whisper           # 语音转录
openai                   # OpenAI API
ffmpeg-python            # FFmpeg Python库（可选）
requests                 # HTTP请求
python-dotenv            # 环境变量管理
flask                    # API服务器
flask-cors               # 跨域支持
```

### 2. 配置 FFmpeg 和 yt-dlp 🆕

**两种方式任选其一：**

#### 方式1：在程序GUI中配置（推荐）⭐

1. 运行程序：`python main.py`
2. 进入"设置"标签页
3. 找到"FFmpeg设置"和"yt-dlp设置"两个区域

**FFmpeg 配置**：
- 模式选择："自动"（推荐）
- 勾选"找不到时自动下载"
- 点击"下载FFmpeg"按钮（Windows用户）
- 或点击"浏览"指定本地ffmpeg.exe
- 点击"测试FFmpeg"验证
- 点击底部"保存设置"

**yt-dlp 配置**：
- 模式选择："自动"（推荐）
- 勾选"找不到时自动下载"
- 点击"下载yt-dlp"按钮
- 或点击"浏览"指定本地yt-dlp
- 点击"测试yt-dlp"验证
- 点击底部"保存设置"

#### 方式2：使用命令行工具

```bash
# FFmpeg 配置
python ffmpeg_config_cli.py status      # 查看状态
python ffmpeg_config_cli.py download    # 下载FFmpeg
python ffmpeg_config_cli.py test        # 测试

# yt-dlp 配置
# (yt-dlp通常随pip install yt-dlp自动安装)
```

#### 方式3：手动安装

**FFmpeg**:
- Windows: 访问 https://www.gyan.dev/ffmpeg/builds/ 下载
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg` 或 `sudo yum install ffmpeg`

**yt-dlp**:
```bash
pip install yt-dlp
```

**详细文档**：
- FFmpeg配置: [FFMPEG_README.md](FFMPEG_README.md)
- yt-dlp配置: [YTDLP_SETUP.md](YTDLP_SETUP.md)
- 双工具配置: [DUAL_VERSION_SETUP.md](DUAL_VERSION_SETUP.md)
- 下载故障排除: [FFMPEG_DOWNLOAD_TROUBLESHOOTING.md](FFMPEG_DOWNLOAD_TROUBLESHOOTING.md)

### 3. 配置 API 密钥

在应用的"设置"标签页中配置：

```env
# OpenAI API (用于GPT模型和Whisper)
OPENAI_API_KEY=sk-your-openai-api-key

# DeepSeek API (国内替代方案)
DEEPSEEK_API_KEY=your-deepseek-api-key

# 代理设置（如需要）
PROXY=http://127.0.0.1:7890
```

### 4. 安装 Chrome 浏览器扩展（可选）

1. 打开 Chrome 浏览器，访问 `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择项目中的 `chrome_extension` 文件夹
5. 扩展将出现在扩展程序列表中

### 5. 运行应用

```bash
# 启动桌面应用
python main.py

# 或使用抖音命令行工具
python douyin_cli.py <抖音视频URL>

# 或使用独立的API服务器
python api_server.py
```

## 📖 使用指南

### 🎬 处理单个视频

1. **复制视频链接**
   - YouTube: `https://www.youtube.com/watch?v=xxxxx` 或 `https://youtu.be/xxxxx`
   - Twitter/X: `https://x.com/user/status/xxxxx` 或 `https://twitter.com/user/status/xxxxx`
   - 抖音: 在App中点击分享→复制链接（支持分享文本自动识别）
   - Bilibili: `https://www.bilibili.com/video/BVxxxxxxxxxx`

2. **粘贴到程序**
   - 在"在线视频"标签页的"视频URL"输入框右键粘贴
   - 程序会自动识别并提取正确的视频链接

3. **选择处理选项**
   - ☑ **下载视频** - 下载完整视频文件（最高可用画质）
   - ☑ **下载音频** - 仅下载音频轨道（节省时间和空间）
   - ☑ **提取字幕** - 使用 Whisper 进行语音转录
   - ☑ **翻译字幕** - 将字幕翻译成目标语言
   - ☑ **生成摘要** - 使用 LLM 生成内容摘要

4. **开始处理**
   - 点击"开始处理"按钮
   - 实时查看处理进度和详细日志
   - 支持随时中断任务

### 批量处理

1. 进入"批量处理"标签页
2. 在文本框中粘贴多个视频链接（每行一个）
3. 支持混合不同平台的链接
4. 点击"开始批量处理"

### 闲时队列

1. 设置闲时时间（如 23:00-07:00）
2. 使用Chrome扩展或程序添加任务到队列
3. 程序会在闲时自动处理队列中的任务

### 直播录制

1. 进入"直播录制"标签页
2. 配置 `live_config/URL_config.ini` 添加直播间
3. 点击"开始监控"
4. 主播开播时自动录制

## 📂 项目结构

```
VideoHub/
├── 📁 核心文件
│   ├── main.py                        # PyQt6 GUI 主程序
│   ├── api_server.py                  # HTTP API 服务器
│   ├── youtube_transcriber.py         # YouTube转录核心
│   ├── douyin_cli.py                  # 抖音命令行工具
│   ├── live_recorder_adapter.py       # 直播录制适配器
│   ├── msg_push.py                    # 消息推送模块
│   └── requirements.txt               # Python 依赖
│
├── 📁 FFmpeg & yt-dlp 管理 🆕
│   ├── ffmpeg_manager.py              # FFmpeg 管理器
│   ├── ffmpeg_config.json             # FFmpeg 配置
│   ├── ffmpeg_install.py              # FFmpeg 安装脚本
│   ├── ffmpeg_config_cli.py           # FFmpeg CLI工具
│   ├── ytdlp_manager.py               # yt-dlp 管理器
│   ├── ytdlp_config.json              # yt-dlp 配置
│   ├── ffmpeg_setup.bat/.sh           # 配置脚本
│   ├── test_ffmpeg_download.py        # 下载测试
│   └── diagnose_ffmpeg_download.py    # 诊断工具
│
├── 📁 Chrome扩展
│   └── chrome_extension/
│       ├── manifest.json              # 扩展配置
│       ├── background.js              # 后台服务
│       ├── content-scripts/           # 页面脚本
│       │   ├── youtube.js
│       │   ├── twitter.js
│       │   ├── bilibili.js
│       │   └── styles.css
│       └── popup/                     # 扩展弹窗
│           ├── popup.html
│           ├── popup.js
│           └── popup.css
│
├── 📁 抖音下载模块
│   └── douyin/
│       ├── parser.py                  # URL解析
│       ├── downloader.py              # 视频下载
│       ├── video_extractor.py         # 视频提取
│       ├── douyinvd_extractor.py      # DouyinVD 提取器
│       ├── dlpanda_extractor.py       # DLPanda 提取器
│       ├── selenium_extractor.py      # Selenium 提取器
│       ├── smart_selenium_extractor.py # 智能 Selenium 提取器
│       ├── ytdlp_wrapper.py           # yt-dlp 包装器
│       ├── advanced_signer.py         # 高级签名
│       ├── config.py                  # 配置文件
│       └── utils.py                   # 工具函数
│
├── 📁 直播录制模块
│   ├── live_recorder/
│   │   ├── spider.py                  # 直播爬虫
│   │   ├── stream.py                  # 流处理
│   │   ├── room.py                    # 直播间管理
│   │   └── ...
│   └── live_config/
│       ├── config.ini                 # 录制配置
│       └── URL_config.ini             # 直播间列表
│
├── 📁 输出目录
│   ├── downloads/                     # 下载的音频文件
│   ├── videos/                        # 下载的视频文件
│   ├── douyin_downloads/              # 抖音视频（如存在）
│   ├── ffmpeg/                        # FFmpeg可执行文件目录 🆕
│   ├── ytdlp/                         # yt-dlp可执行文件目录 🆕
│   ├── transcripts/                   # 转录文本
│   ├── subtitles/                     # 字幕文件
│   ├── summaries/                     # LLM生成的文章摘要
│   └── logs/                          # 程序运行日志
│
├── 📁 配置文件
│   ├── .env                           # 环境变量（API密钥等）
│   ├── ffmpeg_config.json             # FFmpeg配置 🆕
│   ├── ytdlp_config.json              # yt-dlp配置 🆕
│   ├── idle_queue.json                # 闲时队列数据
│   └── templates/                     # 文章生成模板
│
└── 📁 工具脚本
    ├── ffmpeg_setup.bat/.sh           # FFmpeg快速配置脚本
    ├── diagnose_ffmpeg_download.py    # 下载诊断工具 🆕
    ├── test_ffmpeg_download.py        # 下载测试脚本 🆕
    ├── cleanup_test_files.py          # 清理测试文件
    ├── copy_project.py                # 项目复制工具
    └── 带时间戳Tag.bat                 # 批处理工具
```

## 🔧 故障排除

### FFmpeg/yt-dlp 下载失败

1. **运行诊断工具**:
   ```bash
   python diagnose_ffmpeg_download.py
   ```

2. **查看详细日志**:
   - 程序运行时查看控制台输出
   - 找出具体的错误信息

3. **使用手动下载**:
   - 参考 [FFMPEG_MANUAL_DOWNLOAD.md](FFMPEG_MANUAL_DOWNLOAD.md)
   - 下载后使用"浏览"按钮指定路径

4. **设置代理**（如需要）:
   ```bash
   # Windows
   set HTTP_PROXY=http://127.0.0.1:7890
   set HTTPS_PROXY=http://127.0.0.1:7890
   
   # Linux/Mac
   export HTTP_PROXY=http://127.0.0.1:7890
   export HTTPS_PROXY=http://127.0.0.1:7890
   ```

### 视频下载失败

- 检查网络连接
- 确认视频链接有效
- 更新 yt-dlp: `pip install --upgrade yt-dlp`
- 查看程序日志了解详细错误

### Whisper 转录缓慢

- 首次运行会下载模型（~1.5GB）
- 建议使用 GPU 加速（需要安装CUDA版本的PyTorch）
- 可以选择更小的模型（tiny, base, small）
- 长视频建议仅下载音频以加快处理速度

### Chrome 扩展无法连接

- 确保 API 服务器正在运行（`python api_server.py` 或主程序已启动）
- 检查防火墙是否阻止了 5000 端口
- 在扩展弹窗中查看连接状态和错误信息
- 确保扩展已正确加载（检查 chrome://extensions）

## 📝 更新日志

### v2.0.0 - 2024-11-05 🆕

**重大更新**：
- ✅ 新增 FFmpeg 和 yt-dlp 双版本管理系统
- ✅ 支持 Python库 和 可执行文件 两种模式（自动/手动切换）
- ✅ 在设置界面中可视化配置 FFmpeg 和 yt-dlp
- ✅ 一键下载和自动配置功能
- ✅ 新增多个下载源（3个FFmpeg源，GitHub官方yt-dlp源）
- ✅ 下载成功后自动填充路径和保存配置
- ✅ 新增诊断工具和测试脚本（`diagnose_ffmpeg_download.py`）
- ✅ 详细的下载日志和错误处理
- ✅ 完善的文档系统

**改进**：
- 🔧 修复 FFmpeg 下载的字符串拼接错误
- 🔧 改进解压逻辑，智能处理不同压缩包结构
- 🔧 增强错误提示，提供详细的解决方案
- 🔧 优化下载速度（增大块大小到8KB）
- 🔧 添加下载超时和重试机制
- 🔧 完善 GUI 配置界面，支持实时测试和验证

### v1.x.x - 之前版本
- 基础视频处理功能
- Chrome扩展
- 直播录制
- 闲时队列
- 等等...

## 💡 进阶技巧

### 🔐 处理需要登录的视频
某些平台的视频需要登录才能访问，可以通过提供 Cookie 文件来解决：
1. 使用浏览器扩展导出 Cookie（如 "Get cookies.txt"）
2. 在设置中指定 Cookie 文件路径
3. 处理视频时自动使用 Cookie 进行认证

### ⚡ 优化处理速度
- **仅下载音频**：如果只需要转录，跳过视频下载可大幅节省时间
- **选择合适的 Whisper 模型**：
  - `tiny/base`：速度快，准确度较低，适合快速预览
  - `small/medium`：平衡速度和准确度，推荐日常使用
  - `large`：最高准确度，但速度较慢
- **使用 GPU 加速**：安装 CUDA 版本的 PyTorch 可以加速 5-10 倍
- **批量处理**：多个视频一起处理，充分利用系统资源

### 🎨 自定义文章模板
在 `templates/` 目录下创建自定义模板文件：
```
标题：{title}
作者：{author}
时长：{duration}

【内容摘要】
{summary}

【关键要点】
{key_points}
```

### 🌐 使用代理
在 `.env` 文件中配置代理：
```env
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

### 📊 直播录制最佳实践
- **监控间隔**：建议设置 30-60 秒，平衡实时性和服务器压力
- **画质选择**：根据网速选择合适的画质，避免卡顿
- **存储空间**：提前预留足够的磁盘空间，长时间直播可能产生数十GB文件
- **多平台监控**：可同时监控多个直播间，但注意系统资源

## 🛠️ 技术栈

### 核心框架
- **PyQt6** - 跨平台 GUI 框架
- **Flask** - HTTP API 服务器
- **yt-dlp** - 多平台视频下载引擎

### AI/ML
- **OpenAI Whisper** - 语音转录模型
- **PyTorch** - 深度学习框架
- **OpenAI API** - GPT 模型接口
- **DeepSeek API** - 国内 LLM 替代方案

### 视频处理
- **FFmpeg** - 音视频处理工具
- **ffmpeg-python** - FFmpeg Python 封装

### 网络爬虫
- **Selenium** - 浏览器自动化（抖音下载）
- **aiohttp/httpx** - 异步 HTTP 客户端
- **BeautifulSoup4** - HTML 解析
- **requests** - HTTP 请求库

### 其他工具
- **python-dotenv** - 环境变量管理
- **loguru** - 日志系统
- **tqdm** - 进度条显示

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

如果你有好的想法或发现了 Bug，请：
1. 在 GitHub Issues 中搜索是否已有相关问题
2. 提供详细的复现步骤和环境信息
3. 如果可能，附上日志文件和截图

**贡献类型**：
- 🐛 Bug 修复
- ✨ 新功能开发
- 📝 文档改进
- 🌐 新平台支持
- 🎨 UI/UX 优化
- 🔧 性能优化

## 📄 许可证

MIT License

## 💬 联系方式

- GitHub: [your-repo](https://github.com/cacity/VideoHub)
- Issues: [Report Bug](https://github.com/cacity/VideoHub/issues)

---

**提示**: 配置完成后别忘了点击"保存设置"按钮！🎉

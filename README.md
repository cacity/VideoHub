# 视频转录工具 (Video Hub)

这是一个功能强大的桌面应用程序，使用 PyQt6 构建现代化图形界面，支持 **YouTube、Twitter/X、抖音、Bilibili** 等多平台视频内容的智能处理。提供视频下载、语音转录、双语字幕生成、内容摘要等完整工作流，并配备闲时调度、批量处理等高级功能。

## ✨ 加入讨论群

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251223104850735.png)

## ✨ 核心功能

### 🎬 多平台视频处理
- **🎥 平台支持**: YouTube、Twitter/X、抖音、Bilibili 等主流视频平台
- **智能下载**: 支持视频/音频下载，可选择完整视频或仅音频模式
- **精准转录**: 基于 OpenAI Whisper 的高质量语音转录技术
- **多格式字幕**: 生成 .srt、.vtt、.ass 等多种格式的双语字幕文件
- **字幕嵌入**: 支持将字幕直接嵌入到视频文件中
- **内容摘要**: 利用 LLM（支持 OpenAI、DeepSeek 等）智能生成文章摘要

### 🌐 Chrome浏览器扩展
- **页面集成**: 在 YouTube、Twitter/X、Bilibili 视频页面自动添加下载按钮
- **一键加入队列**: 点击按钮即可将视频添加到闲时下载队列
- **队列管理**: 通过扩展弹窗查看、导出、清空下载队列
- **实时同步**: 通过 HTTP API 与桌面应用实时通信
- **智能识别**: 自动提取视频标题、作者、链接等信息
- **视觉反馈**: 添加成功后按钮状态变化，避免重复添加

正确安装插件后，在X/YouTube等视频网站，视频下方会出现下载按钮，后台运行主程序，点下载按钮，直接把下载任务加入到下载列表中。

## 使用方法

### 1.下载油管视频列表

比如斯坦福CS231N这个视频列表：

```
https://www.youtube.com/playlist?list=PLoROMvodv4rOmsNzYBMe0gJY2XS8AQg16
```

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215161701139.png)

复制好视频列表连接，在软件`视频URL`中右键，会直接粘贴视频的连接。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215161801204.png)

勾选下面的选项，可以下载视频，下载原生英文字幕，如果没有原生字幕，可以用whisper转语音转字幕，勾选生成字幕，同时让它翻译，这样就有了视频和双语字幕，方便学习研究。翻译字幕使用的是谷歌翻译，翻译时间会比较久，如果列表中文件比较多，可以先下载视频，视频下载结束后，再选中视频目录，进行单独的字幕提取和翻译。下图就是显示出来的双语字幕。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162320373.png)

### 2.批量翻译字幕

在软件中选中本地视频，勾选批量处理，选中要处理的目录，把要处理的项勾选上，让它自己处理就可以了，这个列表共有18个视频，翻译花了好长时间。仅供参考。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162505994.png)

### 3.抖音视频下载

在抖音PC版上点分享，复制连接，直接在`视频URL`中右键直接粘贴连接，勾选你要处理的项，可以下载和摘取摘要等。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162943458.png)

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215171532304.png)

### 4.下载X视频

类似这种连接，页面有一个视频。

```
https://x.com/tanchibu37099/status/2000362448982102119
```

复制好连接，在`视频URL`中右键直接粘贴连接，即可完成下载。

### 5.插件下载

把项目中的`chrome_extension`整个文件夹拖到Edge或者Chrome浏览器中的扩展中，就完成了插件的安装。安装成功插件栏会有一个图标。在支持的视频正下方会有下载按钮，点击下载按钮，视频就会加入到视频下载列表中进行下载。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215172127386.png)



### 🔄 批量处理

- **多平台批处理**: 支持混合处理不同平台的视频链接
- **文件导入**: 可从文本文件批量导入 URL 列表
- **进度跟踪**: 实时显示批量任务的处理进度和结果

### ⏰ 闲时调度系统
- **智能调度**: 设置闲时时间段（如晚上23:00-早晨07:00），自动执行下载任务
- **任务队列**: 白天将任务添加到队列，闲时自动依次执行
- **灵活控制**: 支持暂停/恢复、立即执行、任务重排等操作
- **可视化管理**: 专门的"闲时队列"标签页，实时查看和管理任务状态

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
- **本地音频/视频**: 处理本地媒体文件
- **批量处理**: 批量处理多个不同平台的视频链接
- **闲时队列**: 可视化任务队列管理和闲时调度控制
- **直播录制**: 多平台直播监控和自动录制管理
- **下载历史**: 查看所有处理过的视频记录
- **设置**: API 配置、模板管理、闲时设置

![image-20250922152348383](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20250923101839756.png)

## 🚀 快速开始

### 📋 功能说明

1.  **复制连接准备**

复制好需要下载的视频的连接，

- YouTube视频地址，如：https://www.youtube.com/watch?v=2WhLmN3dayU 或 https://youtu.be/2WhLmN3dayU ，

- X/Twitter 视频 地址如：https://x.com/tydezhang/status/1970786761849835567 ，

- 抖音 是在视频右下角向右箭头的分享，点复制连接，内容类似：

```
  0.20 z@t.EH CUl:/ 12/21 小伙伴介绍，先出场的就是奥运花样游泳美女 @梁梁梁馨枰 # 吊环 # 危险动作请勿模仿  https://v.douyin.com/KWOa3YB1Lo8/ 复制此链接，打开Dou音搜索，直接观看视频！
```

2. **粘贴**

在上图在线视频标签页，**视频URL**里直接右键，自动粘贴并自动填写正确的连接。

3. **选项勾选**

如果只是下载视频，勾选视频即可，也可下载字幕，转字幕，翻译等工作。下载字幕主要是指油管视频，如果有字幕，会优先下载原版字幕，如果没有，就会调用whisper，进行语音转文字，并制做成字幕。还可以对英文字幕进行翻译，目标文字是中文，制作成双语字幕，并带有新式。

3. **下载**

点击开始处理就开始在后台下载，进行你所勾选的作品，操作成功后会有提示。

4. **其他功能**

还可以对本地视频/音频进行以上的操作，提取字幕，对字幕进行翻译，提取摘要等。

- **单个URL**: 在视频 URL 输入框右键，自动识别并粘贴 YouTube、Twitter、X、抖音等平台链接
- **抖音分享**: 支持直接粘贴抖音分享文本，自动提取其中的视频链接
- **批量URL**: 在批量处理文本框右键，支持粘贴多个不同平台链接或添加到现有链接
- **平台识别**: 自动检测链接类型（YouTube、Twitter/X、抖音、Bilibili 等）并相应处理

## 🛠️ 安装配置

### 系统要求
- Python 3.8+
- Windows/macOS/Linux
- 8GB+ RAM（推荐用于 Whisper 模型）
- FFmpeg（直播录制必需）
- Chrome浏览器（使用浏览器扩展时）

### 1. 环境准备

```bash
# 克隆仓库
git clone git@github.com:cacity/VideoHub.git
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
requests                 # HTTP请求
python-dotenv            # 环境变量管理
flask                    # API服务器
flask-cors               # 跨域支持
asyncio                  # 异步IO（直播录制）
```

### 2. 配置设置

#### API 密钥配置
在应用的"设置"标签页中配置以下 API 密钥：

```env
# OpenAI API (用于GPT模型)
OPENAI_API_KEY=sk-your-openai-api-key

# DeepSeek API (国内替代方案)
DEEPSEEK_API_KEY=your-deepseek-api-key

# 代理设置（如需要）
PROXY=http://proxy.example.com:8080
```

#### 闲时设置
- 默认闲时：23:00 - 07:00
- 可在"设置"或"闲时队列"页面自定义时间段

### 3. 安装 FFmpeg（直播录制必需）

FFmpeg 是直播录制功能的必需组件。应用会自动检测并尝试安装：

```bash
# 运行自动安装脚本
python ffmpeg_install.py
```

手动安装方式：
- **Windows**: 下载 FFmpeg 并添加到系统 PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt-get install ffmpeg` 或 `sudo yum install ffmpeg`

### 4. 安装 Chrome 浏览器扩展（可选）

如果需要使用浏览器扩展功能：

1. 打开 Chrome 浏览器，访问 `chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择项目中的 `chrome_extension` 文件夹
5. 扩展将出现在扩展程序列表中

### 5. 运行应用

```bash
# 启动桌面应用（包含 HTTP API 服务器）
python main.py

# 或使用抖音命令行工具
python douyin_cli.py <抖音视频URL>
```

## 📂 项目结构

```
VideoHub/
├── 📁 核心文件
│   ├── main.py                        # PyQt6 GUI 主程序（整合所有功能）
│   ├── api_server.py                  # HTTP API 服务器（供Chrome扩展调用）
│   ├── douyin_cli.py                  # 抖音命令行下载工具
│   ├── live_recorder_adapter.py       # 直播录制适配器
│   ├── ffmpeg_install.py              # FFmpeg 自动安装脚本
│   ├── msg_push.py                    # 消息推送模块
│   └── requirements.txt               # Python 依赖
├── 📁 Chrome扩展
│   ├── chrome_extension/
│   │   ├── manifest.json              # 扩展配置文件
│   │   ├── background.js              # 后台服务脚本
│   │   ├── content-scripts/           # 页面内容脚本
│   │   │   ├── youtube.js
│   │   │   ├── twitter.js
│   │   │   ├── bilibili.js
│   │   │   └── styles.css
│   │   ├── popup/                     # 扩展弹窗界面
│   │   │   ├── popup.html
│   │   │   ├── popup.js
│   │   │   └── popup.css
│   │   └── icons/                     # 扩展图标
├── 📁 抖音下载模块
│   ├── douyin/                        # 抖音视频解析和下载
│   │   ├── parser.py                  # URL解析
│   │   ├── downloader.py              # 视频下载
│   │   ├── video_extractor.py         # 视频提取器
│   │   └── ...
│   └── douyinVd/                      # Deno实现的备用下载方案
├── 📁 直播录制模块
│   ├── live_recorder/
│   │   ├── spider.py                  # 直播平台爬虫
│   │   ├── stream.py                  # 直播流处理
│   │   ├── room.py                    # 直播间管理
│   │   └── ...
│   └── live_config/
│       ├── config.ini                 # 直播录制配置
│       └── URL_config.ini             # 直播间URL列表
├── 📁 输出目录
│   ├── downloads/                     # 多平台音频文件 (.mp3)
│   ├── videos/                        # 多平台视频文件 (.mp4/.webm/.mov等)
│   ├── douyin_downloads/              # 抖音视频文件 (.mp4 无水印)
│   ├── live_downloads/                # 直播录制文件 (.ts/.flv/.mp4)
│   ├── transcripts/                   # 转录文本 (.txt)
│   ├── subtitles/                     # 字幕文件 (.srt/.vtt/.ass)
│   └── summaries/                     # 文章摘要 (.md)
├── 📁 配置目录
│   ├── templates/                     # 自定义文章模板
│   ├── icons/                         # 应用图标资源
│   └── logs/                          # 下载历史记录
└── 📁 配置文件
    ├── .env                           # 环境变量（API密钥等）
    └── idle_queue.json                # 闲时队列数据
```

## 🌐 支持的平台

### 主要支持平台
- **🎬 YouTube**: 完整支持，包括私有视频（需Cookie）
- **🐦 Twitter/X**: 支持视频推文，可能需要登录状态
- **📱 抖音**: 完整支持，智能分享链接识别，无水印视频下载
- **📺 Bilibili**: 支持 B 站视频下载和处理
- **🌍 其他平台**: 基于 yt-dlp 支持的 1000+ 网站

### 平台特性对比
| 平台 | 视频下载 | 音频提取 | 字幕支持 | Cookie需求 | 特色功能 |
|------|----------|----------|----------|------------|----------|
| YouTube | ✅ 完整支持 | ✅ 高质量 | ✅ 多语言 | 部分视频需要 | 原生字幕提取 |
| Twitter/X | ✅ 支持 | ✅ 支持 | ✅ 转录生成 | 推荐使用 | 短视频优化 |
| 抖音 | ✅ 无水印下载 | ✅ 高质量 | ✅ 转录生成 | 无需要 | 智能分享识别 |
| Bilibili | ✅ 支持 | ✅ 支持 | ✅ 转录生成 | 部分内容需要 | 弹幕处理 |



## 🤝 贡献

欢迎对本项目进行贡献！

### 贡献方式

- 🐛 报告 Bug: [创建 Issue](https://github.com/cacity/VideoHub/issues)
- 💡 功能建议: 提交 Feature Request
- 🔀 代码贡献: 提交 Pull Request
- 📖 文档改进: 完善使用说明

### 开发指南

1. Fork 项目并创建分支
2. 提交代码前请确保通过基本测试
3. 遵循现有代码风格和注释规范
4. 提交 PR 时请详细说明修改内容

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)，允许自由使用、修改和分发。

---

## 🌟 致谢

感谢以下开源项目的支持：

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - 现代化GUI框架
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - 多平台视频下载工具（支持1000+网站）
- [OpenAI Whisper](https://github.com/openai/whisper) - 语音识别模型
- [OpenAI API](https://openai.com/) - 大语言模型服务

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=cacity/VideoHub&type=Date)](https://www.star-history.com/#cacity/VideoHub&Date)

**⭐ 如果这个项目对您有帮助，请给个 Star 支持一下！**

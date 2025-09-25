# 视频转录工具 (Video Hub)

这是一个功能强大的桌面应用程序，使用 PyQt6 构建现代化图形界面，支持 **YouTube、Twitter/X、抖音、Bilibili** 等多平台视频内容的智能处理。提供视频下载、语音转录、双语字幕生成、内容摘要等完整工作流，并配备闲时调度、批量处理等高级功能。

## ✨ 核心功能

### 🎬 多平台视频处理
- **🎥 平台支持**: YouTube、Twitter/X、抖音、Bilibili 等主流视频平台
- **智能下载**: 支持视频/音频下载，可选择完整视频或仅音频模式
- **精准转录**: 基于 OpenAI Whisper 的高质量语音转录技术
- **多格式字幕**: 生成 .srt、.vtt、.ass 等多种格式的双语字幕文件
- **字幕嵌入**: 支持将字幕直接嵌入到视频文件中
- **内容摘要**: 利用 LLM（支持 OpenAI、DeepSeek 等）智能生成文章摘要

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
- **下载历史**: 查看所有处理过的视频记录
- **设置**: API 配置、模板管理、闲时设置

![image-20250922152348383](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20250923101839756.png)

## 🚀 快速开始

### 📋 功能说明

#### "仅转录，不生成文章"选项
- **勾选时**: 只进行视频下载、音频提取、语音转录、字幕生成（如果启用），跳过文章摘要生成
- **不勾选时**: 执行完整流程，包括最终的 LLM 文章摘要生成

#### 闲时操作使用方法
1. **设置闲时**: 在"设置"或"闲时队列"标签页设置闲时时间（默认 23:00-07:00）
2. **添加任务**: 在任意处理页面点击"闲时操作"按钮，将任务加入队列
3. **自动执行**: 到达闲时时间，系统自动依次执行队列中的任务
4. **队列管理**: 在"闲时队列"页面查看、管理、重排任务

#### 智能右键粘贴功能
- **单个URL**: 在视频 URL 输入框右键，自动识别并粘贴 YouTube、Twitter、X、抖音等平台链接
- **抖音分享**: 支持直接粘贴抖音分享文本，自动提取其中的视频链接
- **批量URL**: 在批量处理文本框右键，支持粘贴多个不同平台链接或添加到现有链接
- **平台识别**: 自动检测链接类型（YouTube、Twitter/X、抖音、Bilibili 等）并相应处理

## 🛠️ 安装配置

### 系统要求
- Python 3.8+
- Windows/macOS/Linux
- 8GB+ RAM（推荐用于 Whisper 模型）

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
yt-dlp                   # YouTube下载器
openai-whisper           # 语音转录
openai                   # OpenAI API
requests                 # HTTP请求
python-dotenv            # 环境变量管理
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

### 3. 安装Deno

1. **使用PowerShell安装**:

- 打开PowerShell，输入以下命令以下载和安装Deno:

```powershell
iwr https://deno.land/x/install/install.sh | sh
```
2.**后台运行**

```
deno run --allow-net --allow-read ./douyinVd/main.ts
```



### 4. 运行应用

```bash
# Windows 用户 虚拟环境下运行
python main.py
```

## 📂 项目结构

```
youtube_reader/pyqt7/
├── 📁 核心文件
│   ├── youtube_transcriber_pyqt.py    # PyQt6 GUI 主程序（支持多平台）
│   ├── main.py         # 核心业务逻辑（多平台下载+转录）
│   ├── run.bat                        # Windows 启动脚本
│   └── requirements.txt               # Python 依赖
├── 📁 输出目录
│   ├── downloads/                     # 多平台音频文件 (.mp3)
│   ├── videos/                        # 多平台视频文件 (.mp4/.webm/.mov等)
│   ├── douyin_downloads/              # 抖音视频文件 (.mp4 无水印)
│   ├── transcripts/                   # 转录文本 (.txt)
│   ├── subtitles/                     # 字幕文件 (.srt/.vtt/.ass)
│   └── summaries/                     # 文章摘要 (.md)
├── 📁 配置目录
│   ├── templates/                     # 自定义文章模板
│   ├── icons/                         # 应用图标资源
│   └── logs/                          # 下载历史记录
└── 📁 配置文件
    └── .env                           # 环境变量（API密钥等）
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

### 使用建议
- **YouTube**: 首选平台，功能最完整，支持原生字幕
- **Twitter/X**: 适合短视频处理，建议配置 Cookie
- **抖音**: 国内用户首选，支持无水印下载和智能分享链接识别
- **Bilibili**: 国内用户友好，部分内容需要登录
- **通用**: 所有平台都支持相同的转录和摘要功能

## 🔧 高级功能

### 🎵 抖音特色功能
- **智能分享识别**: 直接粘贴抖音App分享的文本内容，自动提取视频链接
- **无水印下载**: 下载的视频文件自动去除水印，获得原始清晰视频
- **简洁文件名**: 只保留视频标题，去除作者名和ID等冗余信息
- **多种下载源**: 支持多个下载服务，确保下载成功率

### 自定义模板
在"设置"页面可以创建和管理文章生成模板：
- 使用 `{content}` 占位符插入转录内容
- 支持 Markdown 格式
- 预置多种模板样式

### Cookie 支持
处理需要登录的 YouTube 内容：
1. 从浏览器导出 cookies.txt 文件
2. 在相应页面选择 cookie 文件
3. 支持处理私有或地区限制的视频

### 批量处理技巧
- 支持从 .txt 文件导入 URL 列表
- 每行一个链接，支持注释行（#开头）
- 自动跳过重复和无效链接

## 📊 性能优化

### 系统资源
- **CPU**: Whisper 转录时占用较高，建议4核以上
- **内存**: large 模型需要约4GB RAM，medium 模型约2GB
- **存储**: 每小时视频约占用500MB-1GB空间
- **网络**: 下载速度取决于网络环境和 YouTube 服务器

### 性能建议
- 使用 medium Whisper 模型平衡速度和质量
- 闲时处理避免影响日常工作
- 定期清理 downloads 目录节省空间
- 批量处理时避免同时运行其他重负载任务

## 🆘 常见问题

### 下载失败
1. 检查网络连接和代理设置
2. 更新 yt-dlp: `pip install -U yt-dlp`
3. **YouTube**: 某些地区受限视频需要使用 Cookie
4. **Twitter/X**: 可能需要登录状态，建议使用浏览器 Cookie
5. **抖音**: 确保链接有效，支持直接粘贴分享文本
6. 确保视频链接有效且可访问

### 转录质量差
1. 尝试更大的 Whisper 模型（large）
2. 确保音频质量良好
3. 对于特殊口音可尝试指定源语言

### API 调用失败
1. 检查 API 密钥是否正确配置
2. 确认 API 账户有足够余额
3. 检查网络防火墙设置

## 🤝 贡献

欢迎对本项目进行贡献！

### 贡献方式
- 🐛 报告 Bug: [创建 Issue](https://github.com/cacity/youtube_reader/issues)
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

## 交流群

![image-20250925083303544](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20250925083306862.png)


![GitHub stars](https://img.shields.io/github/stars/cacity/VideoHub?style=social)

**⭐ 如果这个项目对您有帮助，请给个 Star 支持一下！**

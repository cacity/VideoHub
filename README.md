# 视频转录工具 (Video Hub)

**当前版本: v0.4.0**

简体中文  | [English](./README_en.md)

VideoHub 是一个基于 PyQt6 的本地视频处理与智能剪辑工作台，支持 **YouTube、Twitter/X、抖音/TikTok、Instagram、Bilibili** 等平台及本地媒体。除了视频下载、音频提取、Whisper 转录、双语字幕、字幕翻译、**AI 配音**和内容摘要，它还通过供 Codex、Claude Code、DeepSeek 等智能助手调用的项目级 Skills，提供基于字幕与画面证据的故事剪辑、影视解说、连续剧批量自动剪辑、音乐卡点、多画幅封面和完整发布包。桌面端同时支持批量处理、闲时队列和剧集目录项目化管理，让多集视频可以按统一配置分阶段处理、复用中间资源并持续调整。

## 付费安装与定制支持

VideoHub 的 MIT 开源版本继续免费。如果你不想自己排查 Python、FFmpeg、TTS 和系列配置，也可以购买固定范围的实施服务：

- **QuickStart 远程安装 — USD 299**：安装配置、一个授权样例、45 分钟交接和 7 天缺陷支持。
- **Creator Series Workflow — USD 999**：统一系列字幕、画幅、音色、封面和三个授权样例。
- **Team Local Deployment — USD 2,999**：团队私有部署、一个定制流程、验收、培训和 30 天缺陷支持。

服务不包括绕过平台限制、处理未授权内容、第三方 API 费用或无限期维护。查看[完整服务范围、验收与付款说明](./SERVICES.md)，或向 [stark fng 发送预填咨询邮件](mailto:gf7823332@gmail.com?subject=VideoHub%20paid%20support&body=Service%20tier%3A%0AOperating%20system%3A%0AWorkflow%20goal%3A%0AAuthorized%20sample%3A%0ATarget%20date%3A%0AIndividual%20or%20team%3A)。

先看证据：[11 期授权艺术内容系列的匿名案例](./CASE_STUDY.md)，包含可在仓库中复核的成片、字幕、章节、发布说明和 44 张多画幅封面；不把内部产出数量包装成客户数量或商业收益。

咨询前可运行 `python src/support_preflight.py`，生成不联网、不含密钥值的环境报告；再按[付费支持申请模板](./SUPPORT_REQUEST.md)提供范围信息，可以更快判断适合的档位与排期。

## 在 Codex / Claude Code 中安装和使用

项目地址：[https://github.com/cacity/VideoHub](https://github.com/cacity/VideoHub)

最简单的使用方式，是把项目地址直接发给运行在本机的 Codex、Claude Code 或其他能够读取文件、执行命令的智能助手，让它完成克隆、依赖检查和本机配置。例如：

```text
请安装并配置这个项目：https://github.com/cacity/VideoHub
把它放到独立项目目录，检查 Python、FFmpeg 和 requirements.txt，安装缺少的依赖，
验证桌面程序和 .agents/skills 下的 VideoHub Skills 是否可用。
需要 API Key 的可选功能先告诉我如何配置，不要把密钥写入代码或提交到 Git。
```

安装完成后，在 VideoHub 项目目录中继续对话，直接提供视频链接、本地文件或剧集目录，再说明成片时长、语言、声音、字幕、画幅和发布平台即可。项目级 Skills 会根据任务自动选择下载、字幕、故事剪辑、影视解说、卡点剪辑或封面流程；如果当前客户端没有自动发现 Skills，可明确要求助手先读取 `.agents/skills/videohub/SKILL.md`。

```text
# YouTube 故事剪辑
使用 VideoHub 处理 https://www.youtube.com/watch?v=VIDEO_ID，先获取原文字幕并理解内容，
剪成 5 分钟的视频，保留原声，生成中英双语字幕，同时给出标题、文案和封面。

# YouTube TTS 解说
把 https://www.youtube.com/watch?v=VIDEO_ID 剪成 8 分钟中文解说版，使用 MiniMax 1.2x，
原声降低到 0.2，关键对话保留原声，输出 1080p 成片和完整发布包。

# 抖音视频
下载并处理 https://v.douyin.com/xxxx/，使用原视频音乐剪成 30 秒卡点视频，
从我提供的素材目录选择镜头，不烧录字幕，生成 3:4、4:3 封面和发布文案。

# 本地电影或连续剧
使用 VideoHub 处理 D:/videos/example.mp4，剪成 10 分钟影视解说；先根据字幕和画面理解剧情，
旁白主导并保留少量关键原声。或者处理 D:/series/example/ 目录下全部剧集，
每集剪成 6 分钟，沿用统一音色、封面和发布包规格，支持断点继续。
```

基础下载、转录、字幕和本地编辑不依赖付费大模型。MiniMax、豆包 TTS、DeepSeek 润色等可选能力需要在本地环境变量或未提交的 `.env` 中配置相应凭据。请只处理自己拥有下载、剪辑和发布权利的素材。

## 智能剪辑与系列生产

最近新增的能力已经从“单次剪一条视频”扩展到可复用的系列生产：

- **连续剧配置驱动批量制作**：`videohub-film-commentary` 新增统一系列执行器。系列级 TTS、音量、画幅、封面和输出路径写入 `series_spec.json`，每集剧情、旁白、选段和发布文案写入 `episode_specs.json`，不再为每个项目复制一份 `build_episode_series.py`。
- **分阶段执行与断点复用**：支持 `preflight`、`prepare`、`render`、`package`、`audit` 和 `all`。修改单集文案后可复用未变化的证据包、视频片段、TTS 分块缓存和发布资产；预检与计划阶段不会调用付费 TTS。
- **剧集目录项目模式**：批量处理本地剧集时，字幕、翻译、转录稿和摘要保存在原视频目录，并生成可移动的 `videohub_project.json`。后续只需给出剧集目录，Skill 会自动定位视频和最佳字幕。
- **五轨时间线精修**：本地网页工作台支持调整视频切点、原声、TTS 旁白、原声窗口和字幕；预览自适应窗口，预览区与时间线可上下拖动调整，解说字幕位置也可手动移动。

连续剧项目可先执行不产生 API 费用的预检：

```powershell
python .agents/skills/videohub-film-commentary/scripts/run_series_commentary.py `
  "workspace/projectNNN_series" --episodes 1-12 --stage preflight
```

配置结构和完整命令见
[series-job-schema.md](./.agents/skills/videohub-film-commentary/references/series-job-schema.md)。

### 工作原理和主要 Skills

VideoHub 的智能剪辑不是简单地按固定时间截取视频，而是让大模型先阅读原文字幕和画面证据，理解人物、主题、事件与因果，再生成可验证的剪辑计划，最后由确定性脚本完成剪辑、翻译、配音、字幕和发布物料。

```mermaid
flowchart LR
    A["视频和字幕"] --> B["证据提取层"]
    B --> C["故事理解层"]
    C --> D["剪辑规划层"]
    D --> E["剪辑后翻译与可选 TTS"]
    E --> F["确定性渲染层"]
    F --> G["短视频、同步字幕和发布包"]
```

| Skill | 主要用途 | 可交付版本 |
| --- | --- | --- |
| `videohub-story-editor` | 把长视频、播客、访谈、课程或知识内容组织成几分钟、叙事完整的短片 | 保留原声的原文/双语字幕版；原声降至约 30% 的 MiniMax 或豆包 TTS 解说版；带 50-100 字文案的抖音发布包 |
| `videohub-film-commentary` | 为电影、电视剧和短剧制作第三者旁白主导的剧情解说 | 旁白与关键影视原声混合版；同步字幕；1080x1920 抖音封面、标题候选、文案、话题和完整发布包 |
| `videohub-beat-editor` | 检测音乐强拍，从长视频或素材目录选择镜头并批量制作卡点视频 | 多画幅成片、歌词字幕、封面、标题、文案和话题 |
| `videohub-cover-designer` | 为单条视频或连续剧建立统一封面体系 | 9:16、3:4、4:3、16:9 封面和小缩略图可读性预览 |

这些剪辑工作流遵循“先理解和剪辑，后重新翻译”的顺序。外文视频不会直接拿剪辑前的逐句机翻决定剧情；最终字幕根据成片时间轴重新生成，并可选用 DeepSeek 做轻度整体润色。影视解说还会保留冲突、揭露、告白、反问、笑点和告别等关键原声，让演员表演和环境声不被旁白完全覆盖。

> 智能剪辑能力通过 `.agents/skills/` 供支持项目级 Skills 的智能助手调用，并复用仓库内的 Python/FFmpeg 脚本；它们不是桌面 GUI 中的一键自动剪辑按钮。

### 可视化时间线精修

AI 完成初剪后，可以在本地网页工作台中继续精修。编辑器会直接打开已有的 `workspace/projectNNN_*` 解说项目，提供视频预览，以及视频、原声、TTS 旁白、原声锚点和字幕五条轨道。可以拖动切点和原声窗口、拆分、删除、重排片段、调整字幕、撤销或重做，并把每次保存写入独立的 `revisions/rev-*`，不会覆盖原始计划和素材。

第二阶段能力也已接入：未变化的视频片段会复用 `.story_editor_cache/segments` 缓存；修改旁白后可以只重新生成对应的 MiniMax 语音块。音量关键帧、片段淡入淡出、交叉转场、多个本地视频源和 DeepSeek 局部改写也可以在同一工作台中设置。最终输出仍由本地 FFmpeg 按保存的时间线确定性渲染。

```powershell
cd frontend
npm install
npm run build

cd ..
python src/story_timeline_server.py
```

然后访问 `http://127.0.0.1:8766/story-editor`。MiniMax 单段重生成和 DeepSeek 改写是可选功能，只有本地配置了对应 API Key 才会调用；没有密钥不影响时间线编辑、保存和渲染。

## 🔊 近期更新：MiniMax 多音色配音

VideoHub 的 AI 配音现在新增 **MiniMax TTS API** 后端。除了原来的本地 Kokoro 和 CosyVoice，用户也可以在设置中切换到 MiniMax，并从多个系统音色中选择更合适的声音。

- **多音色选择**: 支持中文男声、中文女声、新闻播音、电台主持、青年声线、成熟声线和粤语男声等预置音色
- **可试听再生成**: AI 配音页可直接试听当前音色，确认效果后再开始正式配音
- **可自定义 Voice ID**: 除预置音色外，也可以手动填写 MiniMax 控制台中的自定义 `voice_id`
- **不影响默认流程**: 未切换时仍默认使用本地 Kokoro；CosyVoice 和 MiniMax 都是手动选择的可选后端
- **适合视频解说**: 男声播音、主持类音色更适合课程、技术分享、访谈、说明类视频的中文配音
- MiniMax配音的演示视频 youtube https://youtu.be/ns-X5yUb4gE

## ✨ 加入讨论群

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20260713124857253.png)

## ✨ 核心功能

### 🎬 多平台视频处理

- **🎥 平台支持**: YouTube、Twitter/X、抖音、Bilibili 等主流视频平台
- **智能处理**: 支持视频/音频导入与本地处理，可选择完整视频或仅音频模式
- **精准转录**: 基于 OpenAI Whisper 的高质量语音转录技术
- **多格式字幕**: 生成 .srt、.vtt、.ass 等多种格式的双语字幕文件
- **字幕嵌入**: 支持将字幕直接嵌入到视频文件中
- **AI 配音**: 默认使用 Kokoro TTS，也可手动切换到 CosyVoice SFT / Instruct 或 MiniMax API，生成更自然的中文配音版本视频
- **故事剪辑**: 基于原文字幕和画面证据理解长视频，完成选段、重排、剪辑后翻译和同步字幕
- **影视解说**: 第三者 TTS 旁白结合关键影视原声，输出剧情解说成片和抖音封面、标题、文案、话题
- **可视化精修**: 在五轨网页时间线上调整切点、旁白、原声窗口、字幕、音量、淡入淡出和交叉转场，并按修订版本渲染
- **内容摘要**: 利用 LLM（支持 OpenAI、DeepSeek 等）智能生成文章摘要

### 🌐 Chrome浏览器扩展

- **页面集成**: 在 YouTube、Twitter/X、Bilibili 视频页面自动添加处理按钮
- **一键加入队列**: 点击按钮即可将任务添加到闲时处理队列
- **队列管理**: 通过扩展弹窗查看、导出、清空处理队列
- **实时同步**: 通过 HTTP API 与桌面应用实时通信
- **智能识别**: 自动提取视频标题、作者、链接等信息
- **视觉反馈**: 添加成功后按钮状态变化，避免重复添加

正确安装插件后，在X/YouTube等视频网站，视频下方会出现处理按钮，后台运行主程序后，点击按钮即可把当前任务加入处理队列。

### 📱 手机本地网页下载

- **局域网访问**: 在电脑上启动轻量网页端后，iPhone/手机可通过同一 Wi-Fi 下的局域网地址访问
- **手机粘贴链接**: 手机浏览器中长按输入框粘贴视频链接，点击按钮即可触发本地下载
- **下载到手机相册**: 下载完成后页面会提供视频预览、打开视频和下载入口，iPhone 可通过 Safari 分享菜单保存到相册
- **本地保存**: 下载文件统一保存在电脑的 `workspace/mobile/` 目录，便于后续管理和清理

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20260616092447802.png)

启动方式：

```bash
python src/mobile_web_server.py
```

启动后终端会显示类似 `http://局域网IP:8787` 的手机访问地址。手机和电脑需要连接到同一个局域网；如果无法访问，请检查 Windows 防火墙是否允许 `8787` 端口。

## 免责声明

本项目仅供合法、合规且经授权的用途使用。使用涉及第三方平台内容、Cookie、Token、录制、导入或处理功能前，请先阅读 [DISCLAIMER.md](./DISCLAIMER.md)。

## 使用方法

### 1.处理 YouTube 视频列表

比如斯坦福CS231N这个视频列表：

```
https://www.youtube.com/playlist?list=PLoROMvodv4rOmsNzYBMe0gJY2XS8AQg16
```

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215161701139.png)

复制好视频列表连接，在软件`视频URL`中右键，会直接粘贴视频的连接。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215161801204.png)

勾选下面的选项，可以保存视频、获取原生英文字幕；如果没有原生字幕，也可以用 whisper 做语音转字幕，勾选生成字幕并翻译，这样就有了视频和双语字幕，方便学习研究。翻译字幕使用的是谷歌翻译，翻译时间会比较久；如果列表中文件较多，可以先完成媒体处理，再选中视频目录单独进行字幕提取和翻译。下图就是显示出来的双语字幕。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162320373.png)

### 2.批量翻译字幕

在软件中选中本地视频，勾选“批量处理（目录）”。如果目录是一部连续剧或一组相关视频，
保留“剧集项目模式”开关，生成的原文字幕、Google 初译和 DeepSeek 润色版都会写入视频目录
下的 `subtitles/`，转录稿和摘要分别写入 `transcripts/`、`summaries/`。目录中还会生成
`videohub_project.json`，使用故事剪辑或影视解说 Skills 时只需提供这个剧集目录，不必再单独
查找和填写字幕路径。普通单文件处理仍使用全局 `workspace/` 目录，不受影响。

也可以从命令行直接处理一个剧集目录：

```bash
python src/youtube_transcriber.py --video "D:/videos/my_series" --generate-subtitles
```

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162505994.png)

### 3.抖音内容处理

在抖音PC版上点分享，复制连接，直接在`视频URL`中右键直接粘贴连接，勾选你要处理的项，可以进行媒体处理和摘要提取等。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215162943458.png)

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215171532304.png)

### 4.处理 X 视频链接

类似这种连接，页面有一个视频。

```
https://x.com/tanchibu37099/status/2000362448982102119
```

复制好连接，在`视频URL`中右键直接粘贴连接，即可加入处理流程。

### 5.插件使用

把项目中的`chrome_extension`整个文件夹拖到Edge或者Chrome浏览器中的扩展中，就完成了插件安装。安装成功后，扩展栏会有一个图标。在支持的视频正下方会有处理按钮，点击后会把当前任务加入到处理队列中。

![](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20251215172127386.png)



### 🔄 批量处理

- **多平台批处理**: 支持混合处理不同平台的视频链接
- **文件导入**: 可从文本文件批量导入 URL 列表
- **进度跟踪**: 实时显示批量任务的处理进度和结果

### ⏰ 闲时调度系统

- **智能调度**: 设置闲时时间段（如晚上23:00-早晨07:00），自动执行处理任务
- **任务队列**: 白天将任务添加到队列，闲时自动依次执行
- **灵活控制**: 支持暂停/恢复、立即执行、任务重排等操作
- **可视化管理**: 专门的"闲时队列"标签页，实时查看和管理任务状态

### 🎙️ AI 配音

- **样片演示**: [CosyVoice 中文配音合成样片](https://www.youtube.com/watch?v=zigNxozcGEQ)

[![VideoHub 样片演示](https://img.youtube.com/vi/zigNxozcGEQ/hqdefault.jpg)](https://www.youtube.com/watch?v=zigNxozcGEQ)

- **默认后端**: 默认使用原来的 Kokoro TTS，支持晓贝、晓晓、晓艺、云健、云扬等中文音色
- **CosyVoice 后端**: 可在设置中手动切换到 CosyVoice SFT 或 CosyVoice Instruct，支持中文女、中文男、粤语女、英文女等音色
- **MiniMax 后端**: 可在设置中手动切换到 MiniMax API，支持中文男声、中文女声、新闻播音、电台主持、青年声线、成熟声线和粤语男声等系统音色
- **音色试听**: 配音页可直接试听当前音色，试听文件会缓存到 `workspace/dubbing_temp/voice_previews/`，再次试听同一配置时直接播放旧文件
- **智能转录**: 自动将视频语音转录为字幕
- **流畅合成**: 保持原始视频节奏，自动填充静音
- **灵活输出**: 可选择保留原声背景音，调节背景音音量

**输出目录**: 配音文件保存在 `workspace/dubbing_temp/` 目录，完成后生成 `{原文件名}_中文配音.mp4`

#### 使用 CosyVoice 配音

CosyVoice 作为可选本地 TTS 后端，需要先启动独立服务：

```bash
python tts_service.py --host 127.0.0.1 --port 8877
```

服务启动后，在 VideoHub 中进入 `设置 -> TTS 配音设置`：

1. `TTS 引擎版本` 选择 `CosyVoice SFT` 或 `CosyVoice Instruct`
2. 确认 `CosyVoice 服务地址` 为 `http://127.0.0.1:8877`
3. 选择 CosyVoice 音色，例如 `中文女` 或 `中文男`
4. 如果使用 `CosyVoice Instruct`，填写朗读指令，例如“用自然、清晰、适合视频讲解的语气朗读”
5. 保存设置后，到 `AI配音` 页面点击音色旁边的 `试听`
6. 确认音色效果后，选择 YouTube 链接、本地视频或已有字幕，点击 `开始配音`

切换到 CosyVoice 后，AI 配音页的音色列表会自动从 Kokoro 的“晓贝/晓晓/云健”等切换为 CosyVoice 的“中文女/中文男/粤语女”等。未手动切换时，VideoHub 仍保持原来的 Kokoro 配音流程。

#### 使用 MiniMax API 配音

MiniMax 是外部付费 TTS API，适合想快速获得更多中文音色选择、又不想在本地加载大模型的场景。

在 VideoHub 中进入 `设置 -> TTS 配音设置`：

1. `TTS 类型和引擎` 选择 `外部付费 - MiniMax API`
2. 填写 `MiniMax API Key`
3. 选择模型，例如 `speech-2.8-turbo` 或 `speech-2.8-hd`
4. 在 `MiniMax 音色` 中选择男声、女声、播音、主持等预置音色
5. 如需使用自定义声音，可直接在音色框中填写自己的 `voice_id`
6. 保存设置后，到 `AI配音` 页面点击音色旁边的 `试听`
7. 确认音色效果后，选择 YouTube 链接、本地视频或已有字幕，点击 `开始配音`

切换到 MiniMax 后，AI 配音页的音色列表会自动显示 MiniMax 的系统音色。试听和正式配音都会使用当前选中的音色；如果没有配置 MiniMax API Key，不会影响 Kokoro 和 CosyVoice 的本地配音流程。

### 🤖 项目级 Skills

本项目在 `.agents/skills/` 下维护了一组项目级 skills，供 Codex、Claude Code 等智能编码助手读取。它们不是业务运行时依赖，也不会替代 GUI 或 CLI；它们的作用是让智能助手在处理 VideoHub 相关任务时，优先复用当前项目已有入口、脚本和约定，减少重复造轮子或误用过期路径。

| Skill | 适用场景 | 主要复用入口 |
| --- | --- | --- |
| `videohub` | 总入口与任务路由，判断应使用哪个子 skill | `main.py`、`src/youtube_transcriber.py` |
| `videohub-youtube` | YouTube、Twitter/X、Bilibili、本地音视频/文本的转写、字幕、翻译和总结 | `python src/youtube_transcriber.py --help` |
| `videohub-douyin` | 抖音单视频和用户主页作品下载 | `python src/douyin_cli.py <url>` |
| `videohub-queue` | 闲时队列、Chrome/Edge 扩展、本地 API 排查 | `src/api_server.py`、`http://127.0.0.1:8765` |
| `videohub-ffmpeg` | FFmpeg 状态检查、路径配置、模式切换、下载和测试 | `python src/ffmpeg_config_cli.py help` |
| `videohub-subtitles` | 字幕生成后的烧录、视频合成、独立字幕合成工具说明 | `embed_subtitles_to_video()`、`python src/subtitle_merger.py` |
| `videohub-story-editor` | 根据原文字幕和画面证据理解、选段、重排长视频，生成原声双语版、TTS 解说版和抖音发布包 | `.agents/skills/videohub-story-editor/scripts/` |
| `videohub-film-commentary` | 电影、电视剧、短剧的第三者旁白解说、关键原声、同步字幕和抖音封面/标题/文案 | `.agents/skills/videohub-film-commentary/scripts/` |
| `videohub-beat-editor` | 音乐强拍检测、镜头候选选择、歌词字幕和多画幅卡点视频 | `.agents/skills/videohub-beat-editor/scripts/` |
| `videohub-cover-designer` | 影视、连续剧和卡点视频的统一封面及缩略图可读性检查 | `.agents/skills/videohub-cover-designer/scripts/` |
| `videohub-live` | 直播录制依赖、配置和运行状态诊断 | `src/live_recorder_adapter.py` |

#### 使用故事剪辑与影视解说 Skills

安装提示和 YouTube、抖音、本地电影、连续剧批量剪辑示例见本文顶部的
[在 Codex / Claude Code 中安装和使用](#在-codex--claude-code-中安装和使用)。在支持项目级 Skills 的智能助手中，直接描述素材、目标时长、版本、字幕、音色、画幅和发布平台即可。

按照当前项目目录规范，智能助手会为每个任务创建独立的 `workspace/projectNNN_<project_name>/`，并在其中统一保存素材、证据、故事分析、来源映射、剪辑计划、字幕、TTS 缓存、成片、发布物料和 QA 报告。底层脚本仍兼容 `workspace/review_packs/story_editor/`、`workspace/videos_with_subtitles/` 和 `workspace/publish_packages/douyin/` 等默认目录。故事方案和剪辑计划在进入渲染前必须通过数据校验，最终视频还会检查时长、字幕边界和完整解码。

常见同步点：

- 字幕翻译默认使用 Google；如果 Google 失败，会尝试 DeepSeek/OpenAI 作为备用翻译。
- 字幕目标语言支持 `zh-CN`、`zh-TW`、`en`、`ja`、`ko`、`ru`、`fr`、`de`、`es`、`it`、`pt`、`ar`，默认 `zh-CN`。
- 字幕烧录主流程复用 `src/youtube_transcriber.py` 中的 `embed_subtitles_to_video()`；独立 GUI 工具为 `src/subtitle_merger.py`。
- 抖音用户主页下载已有入口，但通常需要有效 Cookie 和相关依赖，实际可用性以运行结果为准。



## 🖼️ 应用界面

### 主界面标签页

- **在线视频**: 单个视频处理，支持 YouTube、Twitter、X、抖音等多平台
- **本地音频/视频**: 处理本地媒体文件
- **批量处理**: 批量处理多个不同平台的视频链接
- **闲时队列**: 可视化任务队列管理和闲时调度控制
- **直播录制**: 多平台直播监控与录制相关功能
- **处理历史**: 查看所有处理过的任务记录
- **设置**: API 配置、模板管理、闲时设置

![image-20250922152348383](https://raw.githubusercontent.com/cacityfauh-ui/MyPic/master/pic/20250923101839756.png)



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
yt-dlp                   # 多平台媒体获取与处理支持
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

# 启动手机本地网页下载服务（局域网访问，默认端口 8787）
python src/mobile_web_server.py

# 启动 CosyVoice TTS 服务（使用 CosyVoice 配音前启动）
python tts_service.py --host 127.0.0.1 --port 8877

# 或使用抖音处理命令行工具
python douyin_cli.py <抖音视频URL>
```

## 📂 项目结构

```
VideoHub/
├── 📁 核心文件
│   ├── main.py                        # PyQt6 GUI 主程序（整合所有功能）
│   ├── api_server.py                  # HTTP API 服务器（供Chrome扩展调用）
│   ├── tts_service.py                 # CosyVoice 本地 TTS 服务
│   ├── douyin_cli.py                  # 抖音命令行处理工具
│   ├── live_recorder_adapter.py       # 直播录制适配器
│   ├── mobile_web_server.py           # 手机局域网网页下载服务
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
├── 📁 项目级 AI Skills
│   └── .agents/skills/
│       ├── videohub-story-editor/      # 长视频故事理解、剪辑、翻译、TTS 和发布包
│       └── videohub-film-commentary/   # 影视解说、关键原声、封面和发布物料
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
│   ├── douyin_downloads/              # 抖音视频输出目录
│   ├── live_downloads/                # 直播录制文件 (.ts/.flv/.mp4)
│   ├── mobile/                        # 手机网页端下载文件
│   ├── transcripts/                   # 转录文本 (.txt)
│   ├── subtitles/                     # 字幕文件 (.srt/.vtt/.ass)
│   ├── summaries/                     # 文章摘要 (.md)
│   ├── review_packs/story_editor/      # 故事证据、分析、剪辑计划和 QA 报告
│   ├── videos_with_subtitles/          # 故事短片和字幕合成视频
│   ├── publish_packages/douyin/        # 抖音视频、封面、标题、文案和话题
│   └── dubbing_temp/                  # AI 配音临时文件
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
- **📱 抖音**: 支持抖音链接识别与媒体处理
- **📺 Bilibili**: 支持 B 站视频处理
- **🌍 其他平台**: 基于 yt-dlp 支持的 1000+ 网站

### 平台特性对比

| 平台      | 媒体处理   | 音频提取 | 字幕支持   | Cookie需求   | 特色功能     |
| --------- | ---------- | -------- | ---------- | ------------ | ------------ |
| YouTube   | ✅ 完整支持 | ✅ 高质量 | ✅ 多语言   | 部分视频需要 | 原生字幕提取 |
| Twitter/X | ✅ 支持     | ✅ 支持   | ✅ 转录生成 | 推荐使用     | 短视频优化   |
| 抖音      | ✅ 支持     | ✅ 高质量 | ✅ 转录生成 | 视场景而定   | 智能分享识别 |
| Bilibili  | ✅ 支持     | ✅ 支持   | ✅ 转录生成 | 部分内容需要 | 弹幕处理     |



## 🤝 贡献

欢迎对本项目进行贡献！

### 贡献方式

- 🐛 报告 Bug: [创建 Issue](https://github.com/cacity/VideoHub/issues)
- 💡 功能建议: 提交 Feature Request
- 🔀 代码贡献: 提交 Pull Request
- 📖 文档改进: 完善使用说明



## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)，允许自由使用、修改和分发。使用涉及第三方平台内容、Cookie、Token、录制或批量处理等功能前，请先阅读 [DISCLAIMER.md](./DISCLAIMER.md)。

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

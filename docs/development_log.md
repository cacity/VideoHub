# VideoHub 开发日志

本文档用于记录 VideoHub 的重要开发变更。每次向 GitHub 提交或推送代码前，必须同步更新本文档，说明本次更新内容、设计思路、实现方式、验证结果和遗留问题。

## 提交前记录要求

每次准备提交 GitHub 前，至少补充以下内容：

- 更新日期和分支/提交范围。
- 本次解决的问题或新增能力。
- 设计思路：为什么这样设计，和原有能力如何衔接。
- 实现方式：涉及的主要文件、模块、接口或配置。
- 验证结果：运行过哪些检查、测试或手动验证。
- 遗留问题：尚未解决的限制、依赖或后续计划。

建议提交前执行：

```bash
git status --short
git diff --check
python -m py_compile main.py
```

如果本次改动涉及新增 Python 模块，应把对应文件一起加入 `py_compile` 检查。

## 2026-06-23：本地视频增加歌曲音频提取

### 更新范围

- 分支：`main`
- 主要文件：
  - `main.py`
  - `src/youtube_transcriber.py`
  - `src/gui/workers/worker_thread.py`
  - `src/paths_config.py`

### 本次更新内容

本次在“本地视频”功能中增加独立的音频提取能力，用于把下载好的歌曲视频、MV 或本地视频批量转成音频文件。

主要内容包括：

- 本地视频页新增“音频提取”区域。
- 支持单个视频文件提取音频。
- 支持目录模式扫描并提取目录中的所有视频音频。
- 音频统一输出到 `workspace/songs/`，方便和 YouTube 音频、临时下载音频区分。
- 提取完成后直接提示是否打开歌曲目录。
- `songs/` 加入统一目录映射和清理工具，但默认不清理，避免误删用户整理好的歌曲音频。

### 设计思路

这个功能不复用原来的“转录/总结”按钮，因为用户提取歌曲音频时通常不需要 Whisper 转写、字幕生成或文章总结。单独提供“提取音频到歌曲目录”按钮，可以让本地视频页同时保留知识处理能力和轻量音频整理能力。

输出目录选择 `workspace/songs/`，而不是继续写入 `workspace/youtube_audio/` 或通用下载目录，原因是歌曲音频属于用户后续可能长期保留和整理的文件，应该从目录上就能看出用途。

### 实现方式

- `src/paths_config.py`
  - 新增 `SONGS_DIR` 和 `LOCAL_SONGS_DIR`。
  - 在 `DIRECTORY_MAP` 中注册 `songs` 和 `local_songs`。

- `src/youtube_transcriber.py`
  - 新增 `extract_audio_from_local_videos()`。
  - 复用现有 `extract_audio_from_video()` 和 FFmpeg 提取逻辑。
  - 目录模式按视频相对路径生成音频文件名，减少不同子目录同名视频互相覆盖的问题。

- `main.py`
  - 本地视频页新增“提取音频到歌曲目录”和“打开歌曲目录”按钮。
  - 新增 `extract_local_video_audio()`，把单文件或目录提取任务交给后台线程执行。
  - 完成回调识别目录结果，提示打开输出目录。
  - 清理工具增加 `songs/` 入口，默认不勾选。

- `src/gui/workers/worker_thread.py`
  - 为拆分后的 WorkerThread 同步增加 `extract_audio` 任务类型。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py src/youtube_transcriber.py src/paths_config.py src/gui/workers/worker_thread.py
git diff --check
```

手动验证建议：

- 在“本地视频”页选择单个 MP4/WebM 文件，点击“提取音频到歌曲目录”，确认 `workspace/songs/` 生成 MP3。
- 切换到目录模式，选择包含多个视频的目录，确认可以批量生成音频。
- 提取完成后确认弹窗打开的是 `workspace/songs/` 目录。
- 在清理工具中确认 `songs/` 可扫描，但“常用选择”不默认勾选。

### 遗留问题和后续计划

- 当前音频统一输出 MP3，后续可以增加输出格式选择，例如 MP3、WAV、FLAC。
- 目录模式目前按支持的视频扩展名扫描，后续可以允许用户自定义扩展名或排除子目录。

## 2026-06-18：网页版官网和在线试用工具规划落地

### 更新范围

- 分支：`main`
- 主要文件：
  - `frontend/src/App.tsx`
  - `frontend/src/lib/api.ts`
  - `frontend/index.html`
  - `website/backend/app.py`
  - `website/backend/database.py`
  - `website/backend/download_service.py`
  - `website/README.md`
  - `website/scripts/deploy_vps.sh`

### 本次更新内容

本次恢复历史提交中的网页端代码，并按“项目官网 + 轻量在线试用工具”的定位重新规划。

主要内容包括：

- 首页从单一字幕下载页改为 VideoHub 项目介绍页。
- 第一屏突出 VideoHub 的核心定位：把长视频变成字幕、笔记和可复用知识资料。
- 在线工具区拆成两个 Tab：
  - YouTube 字幕下载
  - 抖音单视频下载尝试
- 桌面版能力区展示下载、转写、字幕翻译、AI 摘要、AI 配音、闲时队列、本地归档等核心能力。
- 增加使用边界说明，明确网页端不是云端 VideoHub。
- 后端新增抖音单视频下载接口。
- 抖音下载支持粘贴完整分享文本，后端自动提取链接。
- 抖音下载结果以临时文件形式保存，返回下载地址、文件名、大小和有效期。
- 后端增加下载临时目录 TTL 清理和容量上限清理。
- 后端增加基础 IP 频率限制，降低在线下载接口被刷的风险。
- 数据库增加 `download_log`，记录抖音下载请求。
- 部署脚本增加 `data/downloads` 目录创建。

### 设计思路

网站不做完整云端版 VideoHub，而是承担两个角色：一个是让用户理解项目的官网，另一个是让用户轻量体验字幕下载和单视频下载。

这样设计的原因是，VideoHub 的核心能力依赖本地环境，包括 FFmpeg、yt-dlp、Whisper、TTS 模型、磁盘目录和用户自己的配置。如果把完整能力搬到服务器，会很快遇到服务器成本、平台限制、版权边界、队列调度和文件清理问题。因此网页端只保留低门槛试用能力，完整工作流继续引导用户去 GitHub 运行桌面版。

抖音下载能力也被刻意限制为“单个公开视频尝试”。不支持主页批量、不支持登录内容、不支持长期保存文件。页面上也明确提示用户只处理自己有权访问和使用的公开内容。

### 实现方式

- `frontend/src/App.tsx`
  - 重构为项目介绍 + 在线工具 + 桌面版能力 + 使用边界。
  - 增加工具 Tab，在字幕下载和抖音下载之间切换。
  - 抖音下载输入框支持完整分享文本。
  - 结果区域显示临时文件有效期和下载按钮。

- `frontend/src/lib/api.ts`
  - 增加 `OnlineDouyinDownloadResult` 类型。
  - 增加 `requestOnlineDouyinDownload()`。

- `website/backend/download_service.py`
  - 新增抖音下载服务。
  - 提取分享文本中的抖音链接。
  - 限制允许的抖音相关域名。
  - 每次下载使用独立 job 目录。
  - 下载完成后写入 `metadata.json`。
  - 清理过期 job，并按总容量删除最旧目录。

- `website/backend/app.py`
  - 增加 `/api/downloads/douyin`。
  - 增加 `/api/downloads/files/<file_id>`。
  - 下载接口增加基础 IP 频率限制。

- `website/backend/database.py`
  - 增加 `download_log` 表。
  - 增加下载请求日志记录方法。

- `website/README.md`
  - 更新网站定位、接口、临时文件清理、环境变量和部署说明。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile website/backend/app.py website/backend/database.py website/backend/download_service.py website/backend/subtitle_service.py
npm run build --prefix frontend
git diff --check
```

手动验证建议：

- 打开首页，确认第一屏是项目介绍，不再只是字幕下载工具。
- 在线字幕下载输入 YouTube 链接，确认可以返回字幕下载链接。
- 抖音下载输入完整分享文本，确认可以提取链接并返回视频下载链接。
- 检查 `/opt/videohub-site/data/downloads` 是否按 job 目录保存文件。
- 缩短 `VIDEOHUB_DOUYIN_TTL_SECONDS` 后确认过期目录能被清理。

### 遗留问题和后续计划

- 抖音下载依赖 yt-dlp 对当前平台规则的支持，可能因平台变化失败。
- 频率限制目前是进程内存级别，重启会清空，后续可改为 SQLite 或 Redis。
- 抖音下载目前是同步请求，大视频或网络慢时前端会等待，后续可改为 job 轮询。
- 视频下载仍有版权和平台条款边界，页面文案和免责声明需要保持明确。
- `frontend/` 和 `website/` 当前仍属于网页端内容，是否上传 GitHub 需要单独确认。

## 2026-06-18：AI 配音自然度优化和字幕烧录选项

### 更新范围

- 分支：`main`
- 主要文件：
  - `src/dubbing_engine.py`
  - `main.py`
  - `src/gui/workers/worker_thread.py`
  - `docs/development_log.md`

### 本次更新内容

本次更新针对 AI 配音正式成片时“试听自然、实际配音偏硬”的问题做优化，并在 AI 配音流程中增加字幕烧录选项。

主要内容包括：

- CosyVoice 正式配音前会对字幕文本做轻度清理。
- 对缺少句末标点的中文字幕自动补句号，帮助 TTS 模型判断停顿。
- 对过短且时间相邻的字幕片段做小范围合并，减少“一条字幕一句话”的机械感。
- CosyVoice Instruct 模式下，如果用户没有填写指令，会自动使用更适合视频讲解的默认指令。
- AI 配音界面新增“字幕烧录”选项：
  - 不压字幕
  - 压单语字幕
  - 压双语字幕
- 配音流程会先生成中文配音视频，再按用户选择烧录字幕。
- 双语字幕使用原字幕和译文字幕生成临时 ASS 文件，再复用现有字幕烧录流程。

### 设计思路

这次没有简单地更换音色，而是从输入结构上改善 TTS 的朗读条件。试听文本通常是一句完整、带标点、带停顿暗示的话，而实际配音来自字幕文件，常常是短句、碎片、缺少标点。如果直接逐条送给模型，模型每次都会重新起句，听起来就容易偏硬。

因此这次优化的重点是：在不大幅改变字幕时间轴的前提下，把字幕片段整理成更适合 TTS 朗读的文本。自动补标点解决的是停顿判断问题，短句合并解决的是语气频繁重启问题，默认 instruct 指令解决的是用户未配置指令时模型风格过于普通的问题。

字幕烧录则放在配音音轨合成之后处理。这样可以保留原有无字幕配音视频，也可以额外得到带字幕版本，流程更清晰，失败时也不会影响基础配音结果。

### 实现方式

- `src/dubbing_engine.py`
  - 增加 `subtitle_burn_mode` 配置。
  - 增加 CosyVoice 字幕片段预处理逻辑。
  - 增加 `_normalize_tts_text()`，用于清理文本和补句末标点。
  - 增加 `_merge_short_segments()`，用于合并过短且时间相邻的字幕片段。
  - 增加 `_burn_selected_subtitles()`，按选项烧录单语或双语字幕。
  - 增加 `_create_bilingual_ass()`，用原字幕和译文字幕生成双语 ASS。

- `main.py`
  - AI 配音页新增“字幕烧录”下拉框。
  - 开始配音时把字幕烧录模式传给后台 Worker。
  - 日志中显示当前字幕烧录选择。

- `src/gui/workers/worker_thread.py`
  - 同步 `subtitle_burn_mode` 参数。
  - 同步字幕烧录步骤日志。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py src\dubbing_engine.py src\gui\workers\worker_thread.py
git diff --check
```

手动验证建议：

- CosyVoice SFT 模式生成一段配音，确认短字幕不再明显逐字生硬。
- CosyVoice Instruct 模式不填写指令时，确认仍能正常合成。
- 选择“不压字幕”时，只生成普通配音视频。
- 选择“压单语字幕”时，生成带中文字幕的视频。
- 选择“压双语字幕”时，生成带原文和译文两行字幕的视频。

### 遗留问题和后续计划

- 短句合并目前采用保守规则，只合并很短且相邻的字幕，后续可以根据实际样片继续调整阈值。
- 双语字幕目前按字幕顺序配对，如果原字幕和译文字幕段落数量差异较大，可能只能生成部分双语字幕。
- 字幕样式先使用固定 ASS 样式，后续可以接入设置页已有的双语字幕字体和颜色配置。
- 如果用户希望“压字幕后只保留一个最终文件”，后续可以增加输出策略选项。

## 2026-06-17：本地 CosyVoice TTS 配音能力合并

### 更新范围

- 分支：`feature/local-tts-dubbing`
- 合并到：`main`
- 主要提交：
  - `4121109 chore: suppress TensorFlow TTS preview logs`
  - `ff46a36 docs: sync README updates to main`
  - `ab82985 chore: ignore local model and TTS output directories`
  - `b9d76d9 merge: local TTS dubbing feature`

### 本次更新内容

本次更新围绕本地 TTS 配音能力展开，目标是在保留原有默认 TTS 方案的基础上，增加一个可手动切换的 CosyVoice 方案，用于生成质量更好的中文配音。

主要内容包括：

- 新增 `tts_service.py`，使用 FastAPI 封装 CosyVoice 本地服务。
- 支持 CosyVoice SFT、zero-shot、instruct 三类接口。
- 服务启动时加载模型，请求时复用模型，避免每次生成重复加载。
- 长文本按中文标点和换行切分，分段生成后合并为 wav。
- 输出音频保存到 `outputs/` 目录。
- GUI 设置中增加 TTS 后端切换，默认仍使用原有 TTS。
- 选择 CosyVoice 后，配音页音色列表随后端变化。
- 增加音色试听功能，试听文件缓存到 `workspace/dubbing_temp/voice_previews/`。
- 修复试听时 `re` 未导入导致的 `NameError`。
- 抑制 TensorFlow oneDNN 初始化 INFO 日志，减少后台噪声。
- 更新 README，加入 CosyVoice 用法说明和样片链接。
- 新增 `docs/cosyvoice_tts_service.md`，记录 CosyVoice 服务安装、模型目录和运行方式。
- `.gitignore` 增加 `pretrained_models/` 和 `outputs/`，避免提交本地模型和生成音频。

### 设计思路

这次没有把 CosyVoice 模型直接塞进 GUI 主线程，而是拆成独立的本地 FastAPI 服务。这样做主要考虑：

- 模型加载较重，独立服务可以只加载一次，GUI 只通过 HTTP 调用。
- 避免 TTS 模型依赖污染主程序启动流程。
- 后续可以单独重启、替换或优化 TTS 服务，不影响 VideoHub 主界面。
- 保留原有 TTS 作为默认方案，降低新模型不稳定时对用户现有流程的影响。
- GUI 层只暴露“后端选择、服务地址、音色、指令、试听”等必要配置，避免把模型细节暴露给普通使用流程。

音色试听采用缓存策略：相同后端、模式和音色已经生成过试听音频时，后续直接复用旧文件，不再重复调用模型生成。这样可以减少等待时间，也减少本地显存和计算压力。

### 实现方式

主要涉及文件：

- `tts_service.py`
  - FastAPI 服务入口。
  - 提供 `/tts/sft`、`/tts/zero_shot`、`/tts/instruct` 接口。
  - 负责模型加载、文本切分、音频保存和异常处理。

- `src/cosyvoice_tts_client.py`
  - VideoHub 调用 CosyVoice 服务的 HTTP 客户端。
  - GUI 和配音引擎通过它调用本地服务。

- `src/dubbing_engine.py`
  - 扩展 `DubbingTask` 参数，增加 TTS 后端、CosyVoice 地址、模式、音色和指令。
  - 根据后端选择原有 TTS 或 CosyVoice。
  - CosyVoice 模式下按字幕片段生成音频，并按时间戳合并。

- `main.py`
  - 设置页增加 TTS 后端和 CosyVoice 配置。
  - 配音页音色列表根据后端切换。
  - 增加音色试听按钮和试听线程。
  - 增加试听缓存逻辑。
  - 加入 TensorFlow 日志环境变量，减少后台 INFO 输出。

- `src/gui/workers/worker_thread.py`
  - 同步 WorkerThread 参数，让后台任务能收到 TTS 后端和 CosyVoice 配置。

- `README.md`
  - 增加 AI 配音能力说明、样片链接和本地服务启动方式。

- `.gitignore`
  - 忽略 `pretrained_models/`、`outputs/`，避免模型和生成文件进入仓库。

### 验证结果

已执行过的检查：

```bash
python -m py_compile main.py src\dubbing_engine.py src\cosyvoice_tts_client.py src\gui\workers\worker_thread.py tts_service.py
git diff --check
```

手动验证情况：

- CosyVoice 服务可启动。
- SFT 模式生成音质正常。
- GUI 中可以切换 TTS 后端。
- 音色试听可生成并播放。
- 重复试听时可以复用缓存文件。
- TensorFlow oneDNN 提示已通过环境变量压制。

### 遗留问题和后续计划

- CosyVoice 服务需要用户本地提前下载模型，不适合随仓库提交。
- `pretrained_models/` 模型目录体积较大，必须保持忽略。
- zero-shot 音色克隆依赖参考音频路径，后续可以在 GUI 中增加更友好的参考音频选择。
- instruct 模式的指令文本目前较简单，后续可以提供预设模板，例如“自然、稳重、新闻播报、课程讲解”等。
- 当前试听缓存按配置生成文件，后续可以增加清理入口，避免长期积累。
- 不同显卡、CPU 环境下生成速度差异较大，后续需要补充最低配置和推荐配置说明。
- 如果用户没有启动 `tts_service.py` 就切换到 CosyVoice，GUI 需要给出更明确的服务未连接提示。

## 2026-06-21：字幕翻译增加 DeepSeek 可选润色

### 更新内容

- 在设置页增加“Google翻译后使用 DeepSeek 润色中文字幕”开关。
- 默认不开启润色，保持原有翻译流程不变。
- 开启润色后，字幕先按原逻辑完成翻译，再由 DeepSeek 对中文字幕做轻度整体润色。
- 未配置 `DEEPSEEK_API_KEY`、DeepSeek 调用失败或返回格式异常时，自动保留原翻译结果，不影响主流程。
- YouTube、本地音频、本地视频、批量处理、闲时队列、独立字幕翻译和 AI 配音流程都接入同一开关。
- 开启润色时额外保留 Google 初译字幕和 DeepSeek 润色字幕，便于人工查看和对比。

### 设计思路

Google 免费翻译速度快、成本低，但逐句字幕翻译缺少上下文，容易出现术语不统一、中文语序生硬、跨句衔接不自然的问题。直接改成大模型逐句翻译会增加成本和等待时间，也可能破坏字幕条数。

因此本次采用二阶段方案：

```text
原始字幕
  -> Google/当前翻译方式初译
  -> 保存 Google 初译字幕
  -> DeepSeek 轻度润色
  -> 校验条数和 index
  -> 保存 DeepSeek 润色字幕
```

DeepSeek 只处理已翻译好的中文，不负责重译，不修改时间轴，不增删字幕条目。这样既能提升中文自然度，又能降低字幕结构被破坏的风险。

### 实现方式

主要涉及文件：

- `src/youtube_transcriber.py`
  - 新增 `polish_subtitle_translations_with_deepseek()`。
  - 新增 `should_polish_translation()` 和 DeepSeek 返回 JSON 校验逻辑。
  - `translate_subtitle_file()`、`transcribe_audio_unified()`、`process_youtube_video()`、本地音视频和批量处理函数增加 `enable_translation_polish` 参数。
  - Whisper 生成 SRT/VTT/ASS 时改为先统一翻译并可选润色，再写出三种格式，避免不同格式翻译结果不一致。
  - 开启润色时保存 `*_google.srt` 和 `*_polished.srt`，下游配音和字幕烧录默认使用润色版。

- `main.py`
  - 设置页增加润色开关。
  - 保存设置时写入 `TRANSLATION_POLISH_DEEPSEEK`。
  - 各处理入口和闲时队列参数增加 `enable_translation_polish`。
  - 独立字幕翻译线程和 AI 配音任务透传润色开关。

- `src/dubbing_engine.py`
  - `DubbingTask` 增加 `enable_translation_polish`。
  - AI 配音翻译字幕时传入该开关，保证配音使用润色后的中文字幕。

- `src/gui/workers/worker_thread.py`
  - 模块化 WorkerThread 同步润色参数，保持与 `main.py` 内嵌线程一致。

- `src/gui/workers/subtitle_thread.py`
  - 独立字幕翻译线程改为复用 `translate_subtitle_file()`，避免单独实现与主流程不一致。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\youtube_transcriber.py src\dubbing_engine.py src\gui\workers\worker_thread.py src\gui\workers\subtitle_thread.py
```

结果：编译通过。

### 遗留问题和后续计划

- DeepSeek 返回仍有小概率不是合法 JSON，目前按“失败块保留原翻译”处理。
- 润色强度当前固定为轻度，后续可以增加“轻度 / 标准 / 较强”选项。
- 当前主要面向中文字幕润色，其他目标语言暂不启用。
- 后续可以增加术语表输入，例如固定 `agent=智能体`、`prompt=提示词`。

## 2026-06-22：抖音下载默认不生成 JSON 元数据

### 更新内容

- 抖音下载默认不再保存 `_metadata.json` 文件。
- GUI 中“保存元数据”复选框默认改为未勾选。
- CLI 默认关闭 `save_metadata`。
- `DouyinVdExtractor.download_video()` 增加 `save_metadata` 参数，只有显式开启时才写入 JSON。

### 设计思路

普通用户下载抖音视频时主要需要视频文件，JSON 元数据会让下载目录变得杂乱，也容易让用户误以为产生了额外无用文件。因此把元数据保存改为可选能力，默认保持目录干净。

### 实现方式

主要涉及文件：

- `main.py`
  - 抖音下载页“保存元数据”默认取消勾选。

- `src/douyin/config.py`
  - 默认配置 `save_metadata` 改为 `False`。

- `src/douyin/downloader.py`
  - 调用 `DouyinVdExtractor.download_video()` 时传入当前配置的 `save_metadata`。

- `src/douyin/douyinvd_extractor.py`
  - 只有 `save_metadata=True` 时才保存 `_metadata.json`，并把 metadata 文件加入下载结果列表。

- `src/douyin_cli.py`
  - CLI 默认不保存 JSON 元数据，并更新帮助说明。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\douyin_cli.py src\douyin\config.py src\douyin\downloader.py src\douyin\douyinvd_extractor.py src\gui\workers\douyin_threads.py
git diff --check
```

结果：检查通过。

## 2026-06-22：新增 VideoHub 项目宣传文章

### 更新内容

- 新增 `docs/videohub_promotion_article.md`。
- 文章面向公众号、项目推广和普通用户阅读场景。
- 重点介绍 VideoHub 如何把视频变成字幕、笔记、摘要、配音和可复用资料。
- 覆盖 YouTube/本地音视频处理、字幕翻译、DeepSeek 润色、AI 配音、闲时队列、手机本地网页下载等当前核心能力。

### 设计思路

宣传文章不按 README 的说明书结构罗列功能，而是围绕用户场景展开：长视频不好检索、英文视频理解成本高、批量处理耗时间、手机无法直接使用桌面工具等。每个场景对应一个 VideoHub 的能力，让读者先理解为什么需要这个工具，再理解怎么使用。

### 实现方式

主要涉及文件：

- `docs/videohub_promotion_article.md`
  - 开头用收藏视频难复用的场景引入。
  - 中间按使用场景介绍功能。
  - 结尾说明技术实现、使用边界和项目地址。

### 验证结果

已确认文档已创建，内容为 Markdown 格式，可直接用于公众号、博客或项目介绍页二次编辑。

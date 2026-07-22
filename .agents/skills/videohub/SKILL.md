---
name: videohub
description: VideoHub 总入口。用于识别用户要处理的平台或功能，并路由到更具体的 VideoHub skills，如 YouTube、抖音、闲时队列、FFmpeg、字幕、故事剪辑和直播录制。
---

# VideoHub Router

这是 VideoHub 项目的总入口 skill。

## 适用场景
- 用户只说“处理这个链接”但还没明确平台
- 用户想知道 VideoHub 有哪些可用能力
- 用户不确定该用哪个子 skill

## 路由规则
- Douyin / 抖音链接 → `videohub-douyin`
- YouTube / Twitter(X) / Bilibili / 本地音视频 / 文本转写总结 → `videohub-youtube`
- 空闲队列 / Chrome 插件 / 本地 API → `videohub-queue`
- FFmpeg 安装、测试、模式切换 → `videohub-ffmpeg`
- 字幕烧录 / 合成 → `videohub-subtitles`
- 根据字幕选段、重排并生成故事短片，或整理抖音发布包和文案 → `videohub-story-editor`
- 电影、电视剧、短剧的第三者旁白解说、关键影视原声、抖音封面、标题和发布物料 → `videohub-film-commentary`
- 直播录制 / 开播监控 → `videohub-live`

## 使用原则
- 优先复用现有脚本和 GUI，而不是新造后端。
- 只在需要时调用更具体的子 skill。
- 如果用户目标不明确，先澄清是“下载 / 转写 / 翻译 / 总结 / 故事剪辑 / 队列 / 配置 / 直播”。

## 当前后端入口
- GUI：`python main.py`
- 媒体处理 CLI：`python src/youtube_transcriber.py --help`
- 抖音 CLI：`python src/douyin_cli.py <url>`
- FFmpeg 配置 CLI：`python src/ffmpeg_config_cli.py help`
- 字幕烧录 GUI：`python src/subtitle_merger.py`
- 本地队列 API：GUI 启动后由 `src/api_server.py` 在 `127.0.0.1:8765` 提供

## 近期同步点
- 字幕翻译支持 `--target-language {zh-CN,zh-TW,en,ja,ko,ru,fr,de,es,it,pt,ar}`，默认 `zh-CN`。
- 字幕翻译默认 Google；Google 失败时会尝试 DeepSeek/OpenAI 备用翻译。
- 字幕嵌入/烧录主函数是 `src/youtube_transcriber.py` 中的 `embed_subtitles_to_video()`，独立 GUI 工具是 `src/subtitle_merger.py`。
- `live_recorder/` 当前存在；直播功能仍应以 `src/live_recorder_adapter.py` 的导入结果和 GUI 状态为准。

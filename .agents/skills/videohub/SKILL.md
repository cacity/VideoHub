---
name: videohub
description: VideoHub 总入口。用于识别用户要处理的平台或功能，并路由到更具体的 VideoHub skills，如 YouTube、抖音、蔻享、闲时队列、FFmpeg、字幕和直播录制。
---

# VideoHub Router

这是 VideoHub 项目的总入口 skill。

## 适用场景
- 用户只说“处理这个链接”但还没明确平台
- 用户想知道 VideoHub 有哪些可用能力
- 用户不确定该用哪个子 skill

## 路由规则
- Douyin / 抖音链接 → `videohub-douyin`
- koushare.com 链接 → `videohub-koushare`
- YouTube / Twitter(X) / Bilibili / 本地音视频 / 文本转写总结 → `videohub-youtube`
- 空闲队列 / Chrome 插件 / 本地 API → `videohub-queue`
- FFmpeg 安装、测试、模式切换 → `videohub-ffmpeg`
- 字幕烧录 / 合成 → `videohub-subtitles`
- 直播录制 / 开播监控 → `videohub-live`

## 使用原则
- 优先复用现有脚本和 GUI，而不是新造后端。
- 只在需要时调用更具体的子 skill。
- 如果用户目标不明确，先澄清是“下载 / 转写 / 翻译 / 总结 / 队列 / 配置 / 直播”。

## 当前后端入口
- GUI：`python main.py`
- 媒体处理：`python src/youtube_transcriber.py --help`
- 抖音：`python src/douyin_cli.py <url>`
- FFmpeg：`python src/ffmpeg_config_cli.py help`

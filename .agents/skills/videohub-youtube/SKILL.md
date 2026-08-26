---
name: videohub-youtube
description: 处理 YouTube、Twitter(X)、Bilibili 和本地音视频/文本的转写、字幕、翻译与总结。优先复用 src/youtube_transcriber.py 现有 CLI。
allowed-tools: Bash(python src/youtube_transcriber.py*)
---

# VideoHub Media Processing

复用 `F:/work/VideoHub/src/youtube_transcriber.py` 的 CLI；当前 CLI 入口在文件末尾的 `if __name__ == "__main__"`。

## 适用场景
- 处理 YouTube URL
- 批量处理多个 URL
- 转写本地音频 / 视频
- 从文本直接生成总结
- 生成字幕、翻译字幕、烧录字幕
- 选择字幕目标语言
- 查看模板、历史记录、清理工作目录

## 常用命令
```bash
python src/youtube_transcriber.py --youtube "<url>"
python src/youtube_transcriber.py --youtube "<url>" --generate-subtitles
python src/youtube_transcriber.py --youtube "<url>" --generate-subtitles --target-language ja
python src/youtube_transcriber.py --youtube "<url>" --download-video --embed-subtitles
python src/youtube_transcriber.py --audio "path/to/file.mp3"
python src/youtube_transcriber.py --video "path/to/file.mp4" --generate-subtitles
python src/youtube_transcriber.py --video "path/to/file.mp4" --generate-subtitles --target-language ko
python src/youtube_transcriber.py --video "path/to/series" --generate-subtitles
python src/youtube_transcriber.py --video "path/to/file.mp4" --generate-subtitles --series-project
python src/youtube_transcriber.py --text "path/to/file.txt"
python src/youtube_transcriber.py --urls "<url1>" "<url2>"
python src/youtube_transcriber.py --history
python src/youtube_transcriber.py --cleanup-preview
```

## 重要参数
- `--youtube` / `--audio` / `--video` / `--text` / `--batch` / `--urls`
- `--generate-subtitles`
- `--no-translate`
- `--target-language`：支持 `zh-CN`、`zh-TW`、`en`、`ja`、`ko`、`ru`、`fr`、`de`、`es`、`it`、`pt`、`ar`，默认 `zh-CN`
- `--embed-subtitles`
- `--download-video`
- `--transcribe-only`
- `--template` / `--create-template` / `--list-templates`

## 注意
- 这是当前最强的执行型 skill，优先走现有 CLI。
- 对需要登录的 YouTube 内容，可使用 `--cookies`。
- 输出目录遵循 `paths_config.py` 下的 workspace 结构。
- 字幕翻译默认使用 Google；Google 失败时会尝试 DeepSeek/OpenAI 备用翻译。中文目标语言可选 DeepSeek 润色。
- 本地 GUI 里还有“提取本地视频音频到 songs 目录”的功能，对应 `extract_audio_from_local_videos()`，不属于当前 CLI 的主参数。
- 本地目录输入会作为剧集项目处理，在视频目录内建立 `subtitles/`、`transcripts/`、
  `summaries/`、`audio/`、`videos_with_subtitles/` 和 `videohub_project.json`。后续故事剪辑或
  影视解说只需接收该目录并读取项目清单。

## Twitter/X 来源包

- 可以接收来自 TweetClaw/OpenClaw 等工具的已审核公开 X/Twitter 来源包。
- 来源包只应包含规范推文 URL、公开文本或摘录、作者 handle、采集时间、媒体说明和授权边界。
- 之后仍由 VideoHub 执行下载、转写、字幕和总结流程。
- 不要要求或记录 X Cookie、浏览器配置、会话 token、私信或 API key。

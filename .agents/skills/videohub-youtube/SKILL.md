---
name: videohub-youtube
description: 处理 YouTube、Twitter(X)、Bilibili 和本地音视频/文本的转写、字幕、翻译与总结。优先复用 src/youtube_transcriber.py 现有 CLI。
allowed-tools: Bash(python src/youtube_transcriber.py*)
---

# VideoHub Media Processing

复用 `F:/work/VideoHub/src/youtube_transcriber.py:4582` 的 CLI。

## 适用场景
- 处理 YouTube URL
- 批量处理多个 URL
- 转写本地音频 / 视频
- 从文本直接生成总结
- 生成字幕、翻译字幕、烧录字幕
- 查看模板、历史记录、清理工作目录

## 常用命令
```bash
python src/youtube_transcriber.py --youtube "<url>"
python src/youtube_transcriber.py --youtube "<url>" --generate-subtitles
python src/youtube_transcriber.py --youtube "<url>" --download-video --embed-subtitles
python src/youtube_transcriber.py --audio "path/to/file.mp3"
python src/youtube_transcriber.py --video "path/to/file.mp4" --generate-subtitles
python src/youtube_transcriber.py --text "path/to/file.txt"
python src/youtube_transcriber.py --urls "<url1>" "<url2>"
python src/youtube_transcriber.py --history
python src/youtube_transcriber.py --cleanup-preview
```

## 重要参数
- `--youtube` / `--audio` / `--video` / `--text` / `--batch` / `--urls`
- `--generate-subtitles`
- `--no-translate`
- `--embed-subtitles`
- `--download-video`
- `--transcribe-only`
- `--template` / `--create-template` / `--list-templates`

## 注意
- 这是当前最强的执行型 skill，优先走现有 CLI。
- 对需要登录的 YouTube 内容，可使用 `--cookies`。
- 输出目录遵循 `paths_config.py` 下的 workspace 结构。

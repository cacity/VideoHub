---
name: videohub-subtitles
description: 处理字幕生成后的烧录和合成流程。适用于把 ASS 字幕烧录进视频，或指导用户使用现有字幕工具。
---

# VideoHub Subtitles

当前字幕相关能力分两块：
- 生成字幕、翻译字幕：`F:/work/VideoHub/src/youtube_transcriber.py`
- 将字幕烧录进视频：`F:/work/VideoHub/src/subtitle_merger.py`

## 适用场景
- 用户已经有视频和 ASS 字幕，想烧录
- 用户想知道字幕样式和字体配置从哪里来
- 用户需要区分“生成字幕”和“合成视频”两个阶段

## 当前实现边界
- `subtitle_merger.py` 目前是 PyQt GUI 工具，不是独立纯 CLI
- 如果只是生成字幕，应优先走 `videohub-youtube`
- 如果是现有字幕文件与视频合成，优先走字幕合成工具

## 注意
- 这个 skill 目前以引导和正确分流为主
- 后续如果需要，可再把字幕合成补成 CLI 友好的入口

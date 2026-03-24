---
name: videohub-douyin
description: 下载抖音单视频，复用 src/douyin_cli.py。适合处理抖音分享链接、短链接和标准视频链接。
allowed-tools: Bash(python src/douyin_cli.py*)
---

# VideoHub Douyin Download

复用 `F:/work/VideoHub/src/douyin_cli.py:111`。

## 适用场景
- 下载单个抖音视频
- 处理分享文本中的抖音链接
- 指定下载目录

## 常用命令
```bash
python src/douyin_cli.py "https://v.douyin.com/xxxxx/"
python src/douyin_cli.py "https://www.douyin.com/video/xxxxx" -o "workspace/douyin_downloads"
```

## 前置条件
- 需要先启动 douyinVd 服务
- 当前 CLI 会保存视频、元数据，默认也会保存封面

## 注意
- 当前后端以单视频下载为主。
- 用户主页批量下载在后端未完成，不要承诺该能力。
- 若用户给的是分享口令文本，先提取出 URL 再调用 CLI。

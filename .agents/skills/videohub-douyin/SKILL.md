---
name: videohub-douyin
description: 下载抖音单视频或用户主页作品，复用 src/douyin_cli.py。适合处理抖音分享链接、短链接、标准视频链接和用户主页链接。
allowed-tools: Bash(python src/douyin_cli.py*)
---

# VideoHub Douyin Download

复用 `F:/work/VideoHub/src/douyin_cli.py`。

## 适用场景
- 下载单个抖音视频
- 下载用户主页作品
- 处理分享文本中的抖音链接
- 指定下载目录

## 常用命令
```bash
python src/douyin_cli.py "https://v.douyin.com/xxxxx/"
python src/douyin_cli.py "https://www.douyin.com/video/xxxxx" -o "workspace/douyin_downloads"
python src/douyin_cli.py "https://www.douyin.com/user/xxxxx" --cookie "your_cookie" --limit 3
```

## 前置条件
- 单视频下载仍依赖 douyinVd 服务。
- 用户主页批量下载需要有效 Cookie，通常还需要 `f2` 库可用。
- 当前 CLI 默认保存视频和封面，不保存 JSON 元数据，不下载音乐。

## 注意
- 用户主页批量下载已有入口，但失败原因可能是 Cookie 缺失/失效、`f2` 缺失、主页不可访问或解析不到作品；不要在未实际运行前承诺一定可下载。
- 若用户给的是分享口令文本，先提取出 URL 再调用 CLI。

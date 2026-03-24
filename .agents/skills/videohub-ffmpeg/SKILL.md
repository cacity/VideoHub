---
name: videohub-ffmpeg
description: 管理 FFmpeg 配置、模式、路径、下载和可用性测试。直接复用 src/ffmpeg_config_cli.py。
allowed-tools: Bash(python src/ffmpeg_config_cli.py*)
---

# VideoHub FFmpeg Management

复用 `F:/work/VideoHub/src/ffmpeg_config_cli.py:179`。

## 常用命令
```bash
python src/ffmpeg_config_cli.py status
python src/ffmpeg_config_cli.py test
python src/ffmpeg_config_cli.py mode auto
python src/ffmpeg_config_cli.py mode exe
python src/ffmpeg_config_cli.py path "C:/ffmpeg/bin/ffmpeg.exe"
python src/ffmpeg_config_cli.py prefer-exe true
python src/ffmpeg_config_cli.py auto-download true
python src/ffmpeg_config_cli.py download
```

## 适用场景
- 查看当前 FFmpeg 状态
- 切换 `python` / `exe` / `auto` 模式
- 设置 `ffmpeg.exe` 路径
- 测试是否可用
- 下载 FFmpeg

## 注意
- `status` / `test` 属于只读检查
- `mode` / `path` / `prefer-exe` / `auto-download` / `download` 会修改本地配置或环境

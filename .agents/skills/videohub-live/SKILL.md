---
name: videohub-live
description: 处理直播录制相关诊断、配置和使用说明。适用于检查 live recorder 可用性、录制设置和依赖缺失问题。
---

# VideoHub Live Recording

复用 `F:/work/VideoHub/src/live_recorder_adapter.py` 和 `main.py` 中的直播录制页。

## 适用场景
- 检查直播录制功能是否可用
- 说明如何配置监控 URL 和录制参数
- 排查 FFmpeg 或 live_recorder 模块缺失

## 当前已知限制
- `F:/work/VideoHub/src/live_recorder_adapter.py:29` 会尝试导入 `live_recorder`
- 如果项目根目录缺少 `live_recorder/`，则 `LIVE_RECORDER_AVAILABLE = False`
- 在这种情况下，GUI 页面可能存在，但无法真正开始录制

## 推荐操作
- 先检查 live recorder 依赖是否恢复
- 再检查 FFmpeg 是否已安装可用
- 真正录制和监控仍建议走 GUI 页面

## 注意
- 该 skill 当前以诊断和引导为主
- 不要承诺在依赖缺失时仍可正常录制

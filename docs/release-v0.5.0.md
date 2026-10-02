# VideoHub v0.5.0 更新说明

发布日期：2026-10-02

## 版本重点

v0.5.0 聚焦桌面端长时间任务的可用性和重复操作效率：Whisper 转录增加统一的 CPU/GPU 资源策略，“在线视频”标签页的处理选项增加自动记忆。升级后默认采用均衡资源模式，避免转录任务直接占满整机，同时保留手动调优和纯 CPU 运行能力。

## Whisper 资源控制

设置页新增“转录资源设置”，可选择以下模式：

| 模式 | 默认 CPU 线程比例 | 默认 GPU 显存上限 | 任务优先级 |
| --- | ---: | ---: | --- |
| 节能 | 约 30% | 40% | 空闲优先级 |
| 均衡 | 约 50% | 60% | 低于普通应用 |
| 高性能 | 约 80% | 85% | 普通优先级 |

同时支持：

- 自动选择设备、强制仅 CPU、优先 CUDA 三种设备策略。
- 手动指定 CPU 线程上限和 GPU 显存比例。
- 所有 Whisper 入口共享单实例执行锁，防止多个模型同时加载造成 CPU、内存和显存叠加。
- Whisper 执行期间临时降低 Windows 进程优先级，完成后恢复原优先级。
- 视频音频提取阶段的 FFmpeg 默认最多使用 4 个线程。
- 命令行参数与桌面设置保持一致。

相关参数：

```text
--resource-profile eco|balanced|performance
--whisper-device auto|cpu|cuda
--whisper-cpu-threads N
--whisper-gpu-memory-percent N
```

## 在线视频选项记忆

“在线视频”标签页的以下 8 个勾选项会在变化时立即保存，并在下次启动时恢复：

1. 下载完整视频
2. 优先使用原生字幕
3. 执行转录
4. 生成字幕文件
5. 翻译字幕
6. 将字幕嵌入视频
7. 生成文章摘要
8. 显示翻译日志

这些非敏感界面偏好使用 Qt `QSettings` 按当前系统用户保存，不写入仓库，也不会和 API Key 混存在 `.env`。首次运行或尚无历史值时继续采用原有默认状态。

## 升级说明

- 无需迁移配置文件。首次启动 v0.5.0 时，资源策略默认为“均衡”。
- 已存在的 API Key、下载路径、字幕设置和模型设置不会被修改。
- 如需让显卡完全留给其他软件，请在“设置 -> 转录资源设置”中选择“仅 CPU”。
- 手动资源上限写入本机 `.env`；复选框状态由操作系统用户设置存储管理。

## 验证

- `python -m pytest tests -q`：94 项测试通过。
- `python -m py_compile main.py src/resource_policy.py src/ui_preferences.py src/youtube_transcriber.py tests/test_resource_policy.py tests/test_ui_preferences.py`：通过。
- Windows 上验证均衡策略能够限制 PyTorch CPU 线程，并在转录期间临时降低、结束后恢复进程优先级。
- 使用独立 `QSettings` 实例验证三个处理选项保存后可在新实例中恢复。

## 已知边界

- PyTorch 可限制单进程 CUDA 显存比例，但不能保证把 GPU 计算利用率固定在某个百分比。
- 实际资源占用仍会受到 Whisper 模型大小、媒体长度、硬件和驱动版本影响。
- 本版本没有改变现有任务的输出格式和目录结构。

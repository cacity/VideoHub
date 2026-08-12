# USD 149 异步环境诊断交付样例

> 这是一个使用虚构机器信息制作的脱敏样例，用于展示交付结构和判断深度。它不是客户案例、真实订单、免费个案诊断或兼容性保证。

## 1. 申请摘要

- 目标：在一台 Windows 11 电脑上启动 VideoHub，并跑通一个本地 MP4 的字幕提取流程。
- 现象：应用可以打开，但媒体处理任务立即失败，界面只显示“找不到可执行文件”。
- 已提供证据：`support_preflight.py` 的脱敏摘要和一段不含路径、账号或素材信息的错误文本。
- 未提供且本诊断不需要：密码、API Key、Cookie、私有素材、远程登录权限。

## 2. 已确认事实

| 检查 | 结果 | 证据含义 |
|---|---|---|
| Python 3.11 | PASS | 满足当前运行版本要求 |
| 仓库核心文件 | PASS | `main.py`、`requirements.txt` 和 `src` 存在 |
| 必需 Python 包 | PASS | 基础依赖已安装 |
| `ffmpeg` | FAIL | 当前进程的 `PATH` 中找不到可执行文件 |
| `ffprobe` | FAIL | 当前进程的 `PATH` 中找不到可执行文件 |
| 仓库与工作目录写入 | PASS | 短时写入探针成功 |
| 可用磁盘空间 | PASS | 高于 5 GiB 最低预检值 |
| 可选 TTS/LLM 凭据 | 未配置 | 不影响本地 MP4 的基础字幕提取诊断 |

## 3. 根因判断

**高置信度根因：FFmpeg 工具链未安装，或安装目录未进入启动 VideoHub 的进程 `PATH`。**

理由：Python、仓库文件、必需包、目录写入和磁盘均通过；唯一会直接阻断媒体探测与处理的基础检查是 `ffmpeg` 和 `ffprobe`。两者同时缺失也与“任务立即失败、找不到可执行文件”的脱敏错误一致。

当前证据不能判断 FFmpeg 是完全未安装，还是已经安装但当前终端/桌面进程尚未继承新 `PATH`。因此不建议先重装 Python、VideoHub 或全部依赖。

## 4. 按优先级执行的修复步骤

1. 在新的 PowerShell 窗口运行：

   ```powershell
   Get-Command ffmpeg
   Get-Command ffprobe
   ffmpeg -version
   ffprobe -version
   ```

2. 如果两个命令都找不到，安装同一发行包中的 FFmpeg 与 FFprobe，并把包含两个可执行文件的 `bin` 目录加入当前用户 `PATH`。
3. 完全关闭并重新打开 PowerShell 和 VideoHub，避免旧进程继续使用修改前的环境变量。
4. 重新运行：

   ```powershell
   python src/support_preflight.py
   ```

5. 只有当 `executable:ffmpeg` 和 `executable:ffprobe` 都变为 `PASS` 后，再用一段由申请人拥有处理权、长度不超过 30 秒的本地 MP4 验证基础流程。

## 5. 验收检查

本次诊断在以下条件满足时视为已交付；它不以代替客户实际操作或保证第三方服务可用为验收条件：

- 明确区分已确认事实、推断和无法确认事项；
- 给出一个有证据支持的首要根因及置信度；
- 修复步骤按风险和依赖顺序排列；
- 提供客户可自行运行的复核命令；
- 明确下一步成功门槛和仍不包含的范围。

## 6. 无法从现有证据确认

- 具体 FFmpeg 发行包、版本或安装位置；
- GPU 编码、Whisper、外部 TTS 或第三方平台账号是否可用；
- 私有素材、网络环境和未提供的插件是否还有其他问题；
- 执行修复命令后的实际结果。

这些项目只有在修复基础阻断项后，才值得按新证据继续排查。USD 149 档位包含一次与本报告直接相关的公开 Issue 跟进，但不包含远程登录、代安装、代码修改、私有素材处理或无限排障。

---

# USD 149 Async Environment Diagnosis — Delivery Example

> This is a sanitized example built with fictional machine details. It demonstrates the delivery structure and reasoning depth; it is not a customer case, real order, free individual diagnosis, or compatibility guarantee.

## Request summary

The requester wants to launch VideoHub on Windows 11 and run local MP4 subtitle extraction. The app opens, but media processing stops immediately with a sanitized “executable not found” error. No credentials, private media, remote access, or account data are needed for this diagnosis.

## Confirmed evidence

- Python 3.11, repository files, required Python packages, writable directories, and minimum free storage: **PASS**.
- `ffmpeg` and `ffprobe` on the process `PATH`: **FAIL**.
- Optional TTS/LLM credentials: not configured, but not required for this base local-media diagnosis.

## Root-cause assessment

**High confidence: the FFmpeg toolchain is not installed, or its `bin` directory is not visible to the process that launches VideoHub.** The simultaneous `ffmpeg` and `ffprobe` failures explain the immediate executable error, while the other base checks pass. Current evidence cannot distinguish a missing installation from a stale or incomplete `PATH`, so reinstalling Python or all project dependencies is not the first action.

## Prioritized remediation

1. Verify `Get-Command ffmpeg`, `Get-Command ffprobe`, `ffmpeg -version`, and `ffprobe -version` in a new PowerShell window.
2. If absent, install both tools from one FFmpeg distribution and add its `bin` directory to the current-user `PATH`.
3. Restart PowerShell and VideoHub so they inherit the updated environment.
4. Rerun `python src/support_preflight.py`.
5. Test one authorized local MP4 of 30 seconds or less only after both executable checks pass.

## Acceptance and limits

The report is accepted when it separates facts, inference, and unknowns; identifies an evidence-backed primary cause; gives ordered remediation and verification commands; and states the next success gate. It does not include remote access, installation, code changes, private-media handling, third-party account validation, or unlimited troubleshooting. One directly related follow-up in the original public Issue is included.

[Review the full service scope](../SERVICES.md#0-异步环境诊断--usd-149) · [Open a public paid-support request](https://github.com/cacity/VideoHub/issues/new?template=paid-support.yml)

# VideoHub 开发日志

本文档用于记录 VideoHub 的重要开发变更。每次向 GitHub 提交或推送代码前，必须同步更新本文档，说明本次更新内容、设计思路、实现方式、验证结果和遗留问题。

## 提交前记录要求

每次准备提交 GitHub 前，至少补充以下内容：

- 更新日期和分支/提交范围。
- 本次解决的问题或新增能力。
- 设计思路：为什么这样设计，和原有能力如何衔接。
- 实现方式：涉及的主要文件、模块、接口或配置。
- 验证结果：运行过哪些检查、测试或手动验证。
- 遗留问题：尚未解决的限制、依赖或后续计划。

建议提交前执行：

```bash
git status --short
git diff --check
python -m py_compile main.py
```

如果本次改动涉及新增 Python 模块，应把对应文件一起加入 `py_compile` 检查。

## 2026-06-17：本地 CosyVoice TTS 配音能力合并

### 更新范围

- 分支：`feature/local-tts-dubbing`
- 合并到：`main`
- 主要提交：
  - `4121109 chore: suppress TensorFlow TTS preview logs`
  - `ff46a36 docs: sync README updates to main`
  - `ab82985 chore: ignore local model and TTS output directories`
  - `b9d76d9 merge: local TTS dubbing feature`

### 本次更新内容

本次更新围绕本地 TTS 配音能力展开，目标是在保留原有默认 TTS 方案的基础上，增加一个可手动切换的 CosyVoice 方案，用于生成质量更好的中文配音。

主要内容包括：

- 新增 `tts_service.py`，使用 FastAPI 封装 CosyVoice 本地服务。
- 支持 CosyVoice SFT、zero-shot、instruct 三类接口。
- 服务启动时加载模型，请求时复用模型，避免每次生成重复加载。
- 长文本按中文标点和换行切分，分段生成后合并为 wav。
- 输出音频保存到 `outputs/` 目录。
- GUI 设置中增加 TTS 后端切换，默认仍使用原有 TTS。
- 选择 CosyVoice 后，配音页音色列表随后端变化。
- 增加音色试听功能，试听文件缓存到 `workspace/dubbing_temp/voice_previews/`。
- 修复试听时 `re` 未导入导致的 `NameError`。
- 抑制 TensorFlow oneDNN 初始化 INFO 日志，减少后台噪声。
- 更新 README，加入 CosyVoice 用法说明和样片链接。
- 新增 `docs/cosyvoice_tts_service.md`，记录 CosyVoice 服务安装、模型目录和运行方式。
- `.gitignore` 增加 `pretrained_models/` 和 `outputs/`，避免提交本地模型和生成音频。

### 设计思路

这次没有把 CosyVoice 模型直接塞进 GUI 主线程，而是拆成独立的本地 FastAPI 服务。这样做主要考虑：

- 模型加载较重，独立服务可以只加载一次，GUI 只通过 HTTP 调用。
- 避免 TTS 模型依赖污染主程序启动流程。
- 后续可以单独重启、替换或优化 TTS 服务，不影响 VideoHub 主界面。
- 保留原有 TTS 作为默认方案，降低新模型不稳定时对用户现有流程的影响。
- GUI 层只暴露“后端选择、服务地址、音色、指令、试听”等必要配置，避免把模型细节暴露给普通使用流程。

音色试听采用缓存策略：相同后端、模式和音色已经生成过试听音频时，后续直接复用旧文件，不再重复调用模型生成。这样可以减少等待时间，也减少本地显存和计算压力。

### 实现方式

主要涉及文件：

- `tts_service.py`
  - FastAPI 服务入口。
  - 提供 `/tts/sft`、`/tts/zero_shot`、`/tts/instruct` 接口。
  - 负责模型加载、文本切分、音频保存和异常处理。

- `src/cosyvoice_tts_client.py`
  - VideoHub 调用 CosyVoice 服务的 HTTP 客户端。
  - GUI 和配音引擎通过它调用本地服务。

- `src/dubbing_engine.py`
  - 扩展 `DubbingTask` 参数，增加 TTS 后端、CosyVoice 地址、模式、音色和指令。
  - 根据后端选择原有 TTS 或 CosyVoice。
  - CosyVoice 模式下按字幕片段生成音频，并按时间戳合并。

- `main.py`
  - 设置页增加 TTS 后端和 CosyVoice 配置。
  - 配音页音色列表根据后端切换。
  - 增加音色试听按钮和试听线程。
  - 增加试听缓存逻辑。
  - 加入 TensorFlow 日志环境变量，减少后台 INFO 输出。

- `src/gui/workers/worker_thread.py`
  - 同步 WorkerThread 参数，让后台任务能收到 TTS 后端和 CosyVoice 配置。

- `README.md`
  - 增加 AI 配音能力说明、样片链接和本地服务启动方式。

- `.gitignore`
  - 忽略 `pretrained_models/`、`outputs/`，避免模型和生成文件进入仓库。

### 验证结果

已执行过的检查：

```bash
python -m py_compile main.py src\dubbing_engine.py src\cosyvoice_tts_client.py src\gui\workers\worker_thread.py tts_service.py
git diff --check
```

手动验证情况：

- CosyVoice 服务可启动。
- SFT 模式生成音质正常。
- GUI 中可以切换 TTS 后端。
- 音色试听可生成并播放。
- 重复试听时可以复用缓存文件。
- TensorFlow oneDNN 提示已通过环境变量压制。

### 遗留问题和后续计划

- CosyVoice 服务需要用户本地提前下载模型，不适合随仓库提交。
- `pretrained_models/` 模型目录体积较大，必须保持忽略。
- zero-shot 音色克隆依赖参考音频路径，后续可以在 GUI 中增加更友好的参考音频选择。
- instruct 模式的指令文本目前较简单，后续可以提供预设模板，例如“自然、稳重、新闻播报、课程讲解”等。
- 当前试听缓存按配置生成文件，后续可以增加清理入口，避免长期积累。
- 不同显卡、CPU 环境下生成速度差异较大，后续需要补充最低配置和推荐配置说明。
- 如果用户没有启动 `tts_service.py` 就切换到 CosyVoice，GUI 需要给出更明确的服务未连接提示。

# CosyVoice TTS 服务方案

本文记录 `tts_service.py` 的安装、模型准备、运行和接口调用方式。该服务是 VideoHub 的本地 TTS 试验服务，基于 CosyVoice-300M 系列模型，用 FastAPI 对外提供 HTTP 接口。

## 功能范围

- `/tts/sft`: 使用 `CosyVoice-300M-SFT` 做预置音色合成。
- `/tts/zero_shot`: 使用 `CosyVoice-300M` 做参考音频音色克隆。
- `/tts/instruct`: 使用 `CosyVoice-300M-Instruct` 做带指令的朗读。
- 服务启动时加载模型，请求时复用已加载模型。
- 长文本会按中文标点 `。！？；` 和换行切分，每段尽量不超过 100-150 字。
- 多段音频会合并成一个 wav。
- 输出文件保存到 `outputs/`，接口返回生成的 wav 文件路径。

## 安装

建议单独创建环境，避免 CosyVoice 依赖影响 VideoHub 主程序。

```bash
conda create -n videohub-cosyvoice python=3.10 -y
conda activate videohub-cosyvoice

pip install fastapi uvicorn pydantic torch torchaudio modelscope huggingface_hub
```

克隆 CosyVoice 官方仓库：

```bash
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git F:\work\CosyVoice
cd F:\work\CosyVoice
pip install -r requirements.txt
```

如果子模块下载失败，进入 CosyVoice 目录后重复执行：

```bash
git submodule update --init --recursive
```

## 下载模型

在 VideoHub 根目录执行，PowerShell 示例：

```powershell
@'
from modelscope import snapshot_download

snapshot_download('iic/CosyVoice-300M', local_dir='pretrained_models/CosyVoice-300M')
snapshot_download('iic/CosyVoice-300M-SFT', local_dir='pretrained_models/CosyVoice-300M-SFT')
snapshot_download('iic/CosyVoice-300M-Instruct', local_dir='pretrained_models/CosyVoice-300M-Instruct')
'@ | python -
```

海外网络也可以使用 Hugging Face：

```powershell
@'
from huggingface_hub import snapshot_download

snapshot_download('FunAudioLLM/CosyVoice-300M', local_dir='pretrained_models/CosyVoice-300M')
snapshot_download('FunAudioLLM/CosyVoice-300M-SFT', local_dir='pretrained_models/CosyVoice-300M-SFT')
snapshot_download('FunAudioLLM/CosyVoice-300M-Instruct', local_dir='pretrained_models/CosyVoice-300M-Instruct')
'@ | python -
```

## 环境变量

PowerShell 示例：

```powershell
$env:COSYVOICE_REPO_PATH = "F:\work\CosyVoice"
$env:COSYVOICE_SFT_MODEL_DIR = "F:\work\VideoHub\pretrained_models\CosyVoice-300M-SFT"
$env:COSYVOICE_ZERO_SHOT_MODEL_DIR = "F:\work\VideoHub\pretrained_models\CosyVoice-300M"
$env:COSYVOICE_INSTRUCT_MODEL_DIR = "F:\work\VideoHub\pretrained_models\CosyVoice-300M-Instruct"
$env:COSYVOICE_OUTPUT_DIR = "F:\work\VideoHub\outputs"
```

如果模型放在默认目录 `pretrained_models/` 下，可以只设置：

```powershell
$env:COSYVOICE_REPO_PATH = "F:\work\CosyVoice"
```

## 启动服务

```bash
python tts_service.py --host 127.0.0.1 --port 8877
```

健康检查：

```powershell
curl.exe http://127.0.0.1:8877/health
```

## 接口示例

### SFT 预置音色

```powershell
curl.exe -X POST http://127.0.0.1:8877/tts/sft ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"你好，这是 VideoHub 的本地语音合成测试。\",\"speaker\":\"中文女\"}"
```

说明：`speaker` 必须是 `CosyVoice-300M-SFT` 模型支持的音色 ID。可在 CosyVoice Python 环境里调用 `list_avaliable_spks()` 查看。

### Zero-shot 音色克隆

```powershell
curl.exe -X POST http://127.0.0.1:8877/tts/zero_shot ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"这是一段用参考音频音色生成的新语音。\",\"prompt_text\":\"参考音频对应的原文。\",\"prompt_wav_path\":\"F:\\work\\VideoHub\\samples\\prompt.wav\"}"
```

要求：

- `prompt_wav_path` 必须存在。
- `prompt_text` 应准确对应参考音频内容。
- 服务内部会按 16k 读取参考音频。

### Instruct 指令朗读

```powershell
curl.exe -X POST http://127.0.0.1:8877/tts/instruct ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"今天的视频内容到这里就结束了。\",\"speaker\":\"中文女\",\"instruction\":\"用温柔、自然、稍慢的语气朗读\"}"
```

## 返回格式

```json
{
  "success": true,
  "file_path": "F:\\work\\VideoHub\\outputs\\sft_20260617_120000_ab12cd34.wav",
  "segments": 1,
  "sample_rate": 22050,
  "elapsed_seconds": 2.31
}
```

## 异常处理

服务会处理以下错误：

- 模型目录不存在：启动失败并打印具体目录。
- CosyVoice 未安装或无法导入：启动失败。
- `text` 为空：返回 400。
- `speaker` / `instruction` / `prompt_text` 为空：返回 400。
- `prompt_wav_path` 不存在：返回 400。
- 生成过程失败：返回 500，并带失败原因。

## 后续接入 VideoHub 的建议

当前分支已经把该服务作为可选 TTS 后端接入 VideoHub。默认仍使用原来的 Kokoro TTS，不会自动切换。

在 GUI 中切换：

```text
设置 -> TTS 配音设置 -> TTS 引擎版本
```

可选项：

- `Kokoro（原版，默认）`
- `CosyVoice SFT`
- `CosyVoice Instruct`

切换到 CosyVoice 前，需要先启动服务：

```bash
python tts_service.py --host 127.0.0.1 --port 8877
```

切换 TTS 引擎后，AI 配音页的 `配音音色` 会自动更新：

- Kokoro：显示晓贝、晓晓、晓艺、云健、云扬。
- CosyVoice：显示中文女、中文男、日语男、粤语女、英文女、英文男、韩语女。

`配音音色` 右侧的 `试听` 按钮会用当前后端生成一小段 wav，并用系统默认播放器打开。
试听音频会缓存到 `workspace/dubbing_temp/voice_previews/`。相同后端、模式、音色、语速、试听文本和 Instruct 指令再次试听时，会直接播放旧文件；缓存文件不存在时才重新生成。

VideoHub GUI 会调用本地 HTTP 接口：

```text
字幕文本 -> /tts/sft 或 /tts/zero_shot 或 /tts/instruct -> wav -> ffmpeg 合成视频
```

这样 CosyVoice 的重依赖、模型加载和显存占用不会直接影响主 GUI 启动。

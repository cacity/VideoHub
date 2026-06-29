"""FastAPI service for CosyVoice based text-to-speech.

This service is intentionally independent from the PyQt GUI. It loads the
CosyVoice models once at startup and exposes HTTP endpoints that VideoHub or
other local clients can call.
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import torch
import torchaudio
import onnxruntime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"
DEFAULT_SFT_MODEL_DIR = ROOT_DIR / "pretrained_models" / "CosyVoice-300M-SFT"
DEFAULT_ZERO_SHOT_MODEL_DIR = ROOT_DIR / "pretrained_models" / "CosyVoice-300M"
DEFAULT_INSTRUCT_MODEL_DIR = ROOT_DIR / "pretrained_models" / "CosyVoice-300M-Instruct"

MAX_SEGMENT_CHARS = 140
MIN_SEGMENT_CHARS = 100


class ServiceConfig:
    sft_model_dir: Path = Path(os.getenv("COSYVOICE_SFT_MODEL_DIR", DEFAULT_SFT_MODEL_DIR))
    zero_shot_model_dir: Path = Path(os.getenv("COSYVOICE_ZERO_SHOT_MODEL_DIR", DEFAULT_ZERO_SHOT_MODEL_DIR))
    instruct_model_dir: Path = Path(os.getenv("COSYVOICE_INSTRUCT_MODEL_DIR", DEFAULT_INSTRUCT_MODEL_DIR))
    output_dir: Path = Path(os.getenv("COSYVOICE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    cosyvoice_repo_path: str = os.getenv("COSYVOICE_REPO_PATH", "")
    fp16: bool = os.getenv("COSYVOICE_FP16", "0").lower() in {"1", "true", "yes", "on"}


class ModelSlot:
    def __init__(self) -> None:
        self.model: Any | None = None
        self.lock = threading.Lock()


class CosyVoiceState:
    def __init__(self) -> None:
        self.sft = ModelSlot()
        self.zero_shot = ModelSlot()
        self.instruct = ModelSlot()
        self.load_wav: Callable[[str, int], Any] | None = None
        self.device: str = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch_cuda_available: bool = torch.cuda.is_available()
        self.torch_cuda_device_name: str | None = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        self.onnxruntime_providers: list[str] = onnxruntime.get_available_providers()


STATE = CosyVoiceState()


class SFTRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    speaker: str = Field(..., description="SFT speaker id from the CosyVoice model.")


class ZeroShotRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    prompt_text: str = Field(..., description="Transcript of the prompt wav.")
    prompt_wav_path: str = Field(..., description="Path to the reference wav file.")


class InstructRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    speaker: str = Field(..., description="Speaker id from the CosyVoice instruct model.")
    instruction: str = Field(..., description="Speaking style instruction.")


class TTSResponse(BaseModel):
    success: bool
    file_path: str
    segments: int
    sample_rate: int
    elapsed_seconds: float


def _add_cosyvoice_paths() -> None:
    """Allow running this service from VideoHub while CosyVoice is cloned elsewhere."""
    if ServiceConfig.cosyvoice_repo_path:
        repo_path = Path(ServiceConfig.cosyvoice_repo_path).resolve()
        if str(repo_path) not in sys.path:
            sys.path.insert(0, str(repo_path))

        matcha_path = repo_path / "third_party" / "Matcha-TTS"
        if matcha_path.exists() and str(matcha_path) not in sys.path:
            sys.path.insert(0, str(matcha_path))


def _require_model_dir(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise RuntimeError(f"{label} 模型目录不存在: {resolved}")
    return resolved


def _load_models() -> None:
    _add_cosyvoice_paths()
    ServiceConfig.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from cosyvoice.cli.cosyvoice import CosyVoice
        from cosyvoice.utils.file_utils import load_wav
    except Exception as exc:
        raise RuntimeError(
            "无法导入 CosyVoice。请先安装 CosyVoice，并设置 COSYVOICE_REPO_PATH 或 PYTHONPATH。"
        ) from exc

    sft_dir = _require_model_dir(ServiceConfig.sft_model_dir, "CosyVoice-300M-SFT")
    zero_shot_dir = _require_model_dir(ServiceConfig.zero_shot_model_dir, "CosyVoice-300M")
    instruct_dir = _require_model_dir(ServiceConfig.instruct_model_dir, "CosyVoice-300M-Instruct")

    if ServiceConfig.fp16 and not torch.cuda.is_available():
        raise RuntimeError("COSYVOICE_FP16=1 需要可用的 CUDA GPU")

    print(
        "CosyVoice device:",
        STATE.device,
        "| torch cuda:",
        STATE.torch_cuda_available,
        STATE.torch_cuda_device_name or "",
        "| onnxruntime providers:",
        STATE.onnxruntime_providers,
        "| fp16:",
        ServiceConfig.fp16,
        flush=True,
    )

    STATE.sft.model = CosyVoice(str(sft_dir), fp16=ServiceConfig.fp16)
    STATE.zero_shot.model = CosyVoice(str(zero_shot_dir), fp16=ServiceConfig.fp16)
    STATE.instruct.model = CosyVoice(str(instruct_dir), fp16=ServiceConfig.fp16)
    STATE.load_wav = load_wav


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        _load_models()
    except Exception as exc:
        # Raising here makes startup fail loudly instead of accepting requests
        # that cannot be served.
        raise RuntimeError(f"CosyVoice TTS 服务启动失败: {exc}") from exc
    yield


app = FastAPI(
    title="VideoHub CosyVoice TTS Service",
    description="Local FastAPI wrapper for CosyVoice-300M TTS models.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "models_loaded": {
            "sft": STATE.sft.model is not None,
            "zero_shot": STATE.zero_shot.model is not None,
            "instruct": STATE.instruct.model is not None,
        },
        "runtime": {
            "device": STATE.device,
            "torch_version": torch.__version__,
            "torch_cuda_available": STATE.torch_cuda_available,
            "torch_cuda_version": torch.version.cuda,
            "torch_cuda_device_name": STATE.torch_cuda_device_name,
            "onnxruntime_providers": STATE.onnxruntime_providers,
            "onnxruntime_cuda_available": "CUDAExecutionProvider" in STATE.onnxruntime_providers,
            "fp16": ServiceConfig.fp16,
        },
        "output_dir": str(ServiceConfig.output_dir.resolve()),
    }


@app.post("/tts/sft", response_model=TTSResponse)
def tts_sft(payload: SFTRequest) -> TTSResponse:
    text = _normalize_text(payload.text)
    speaker = payload.speaker.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    if not speaker:
        raise HTTPException(status_code=400, detail="speaker 不能为空")

    return _run_tts(
        mode="sft",
        text=text,
        slot=STATE.sft,
        infer=lambda model, segment: model.inference_sft(segment, speaker, stream=False),
    )


@app.post("/tts/zero_shot", response_model=TTSResponse)
def tts_zero_shot(payload: ZeroShotRequest) -> TTSResponse:
    text = _normalize_text(payload.text)
    prompt_text = _normalize_text(payload.prompt_text)
    prompt_wav_path = Path(payload.prompt_wav_path).expanduser().resolve()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    if not prompt_text:
        raise HTTPException(status_code=400, detail="prompt_text 不能为空")
    if not prompt_wav_path.exists() or not prompt_wav_path.is_file():
        raise HTTPException(status_code=400, detail=f"参考音频不存在: {prompt_wav_path}")
    if STATE.load_wav is None:
        raise HTTPException(status_code=503, detail="CosyVoice load_wav 未初始化")

    try:
        prompt_speech_16k = _load_prompt_wav(prompt_wav_path, 16000)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"参考音频读取失败: {exc}") from exc

    return _run_tts(
        mode="zero_shot",
        text=text,
        slot=STATE.zero_shot,
        infer=lambda model, segment: model.inference_zero_shot(segment, prompt_text, prompt_speech_16k, stream=False),
    )


@app.post("/tts/instruct", response_model=TTSResponse)
def tts_instruct(payload: InstructRequest) -> TTSResponse:
    text = _normalize_text(payload.text)
    speaker = payload.speaker.strip()
    instruction = _normalize_text(payload.instruction)
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")
    if not speaker:
        raise HTTPException(status_code=400, detail="speaker 不能为空")
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction 不能为空")

    def infer(model: Any, segment: str):
        if hasattr(model, "inference_instruct"):
            return model.inference_instruct(segment, speaker, instruction, stream=False)
        if hasattr(model, "inference_instruct2"):
            return model.inference_instruct2(segment, instruction, stream=False)
        raise RuntimeError("当前 CosyVoice 模型不支持 instruct 推理接口")

    return _run_tts(mode="instruct", text=text, slot=STATE.instruct, infer=infer)


def _run_tts(
    *,
    mode: str,
    text: str,
    slot: ModelSlot,
    infer: Callable[[Any, str], Any],
) -> TTSResponse:
    if slot.model is None:
        raise HTTPException(status_code=503, detail=f"{mode} 模型未加载")

    started_at = time.time()
    segments = split_text(text)
    if not segments:
        raise HTTPException(status_code=400, detail="文本分段后为空")

    output_path = _make_output_path(mode)
    try:
        with slot.lock:
            audios = []
            sample_rate = int(getattr(slot.model, "sample_rate", 22050))
            for segment in segments:
                chunk = _collect_inference_audio(infer(slot.model, segment))
                if chunk is None:
                    raise RuntimeError(f"生成失败，未返回音频: {segment[:30]}")
                audios.append(_ensure_2d_audio(chunk.detach().cpu()))

        if not audios:
            raise RuntimeError("生成失败，未得到任何音频")

        merged_audio = torch.cat(audios, dim=1)
        _save_wav(output_path, merged_audio, sample_rate)
        return TTSResponse(
            success=True,
            file_path=str(output_path.resolve()),
            segments=len(segments),
            sample_rate=sample_rate,
            elapsed_seconds=round(time.time() - started_at, 3),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{mode} 语音生成失败: {exc}") from exc


def _collect_inference_audio(result_iter: Any) -> torch.Tensor | None:
    tensors: list[torch.Tensor] = []
    for item in result_iter:
        speech = item.get("tts_speech") if isinstance(item, dict) else None
        if speech is None:
            continue
        if not isinstance(speech, torch.Tensor):
            speech = torch.as_tensor(speech)
        tensors.append(_ensure_2d_audio(speech.detach().cpu()))
    if not tensors:
        return None
    return torch.cat(tensors, dim=1)


def _ensure_2d_audio(audio: torch.Tensor) -> torch.Tensor:
    if audio.ndim == 1:
        return audio.unsqueeze(0)
    if audio.ndim == 2:
        return audio
    raise ValueError(f"不支持的音频张量维度: {tuple(audio.shape)}")


def _save_wav(output_path: Path, audio: torch.Tensor, sample_rate: int) -> None:
    """Save wav with torchaudio first, falling back on Windows codec issues."""
    try:
        torchaudio.save(str(output_path), audio, sample_rate)
        return
    except Exception as torchaudio_error:
        try:
            import soundfile as sf

            sf.write(str(output_path), audio.squeeze(0).numpy(), sample_rate)
            return
        except Exception as soundfile_error:
            raise RuntimeError(
                f"音频保存失败: torchaudio={torchaudio_error}; soundfile={soundfile_error}"
            ) from soundfile_error


def _load_prompt_wav(prompt_wav_path: Path, sample_rate: int) -> torch.Tensor:
    if STATE.load_wav is not None:
        try:
            return STATE.load_wav(str(prompt_wav_path), sample_rate)
        except Exception:
            pass

    import librosa
    import soundfile as sf

    audio, source_rate = sf.read(str(prompt_wav_path), always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if source_rate != sample_rate:
        audio = librosa.resample(audio, orig_sr=source_rate, target_sr=sample_rate)
    return torch.from_numpy(audio).float()


def _make_output_path(mode: str) -> Path:
    ServiceConfig.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return ServiceConfig.output_dir / f"{mode}_{timestamp}_{uuid.uuid4().hex[:8]}.wav"


def _normalize_text(text: str) -> str:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t\f\v]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def split_text(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
    """Split text by Chinese punctuation/newlines, keeping each segment modest."""
    text = (text or "").strip()
    if not text:
        return []

    pieces = [piece.strip() for piece in re.split(r"(?<=[。！？；\n])", text) if piece.strip()]
    if not pieces:
        pieces = [text]

    segments: list[str] = []
    buffer = ""
    for piece in pieces:
        while len(piece) > max_chars:
            head = piece[:max_chars]
            cut_at = max(head.rfind("，"), head.rfind(","), head.rfind("、"), head.rfind(" "))
            if cut_at < MIN_SEGMENT_CHARS:
                cut_at = max_chars
            part = piece[:cut_at].strip()
            if part:
                if buffer:
                    segments.append(buffer)
                    buffer = ""
                segments.append(part)
            piece = piece[cut_at:].strip()

        if not piece:
            continue
        if not buffer:
            buffer = piece
        elif len(buffer) + len(piece) <= max_chars:
            buffer += piece
        else:
            segments.append(buffer)
            buffer = piece

    if buffer:
        segments.append(buffer)
    return segments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VideoHub CosyVoice FastAPI TTS service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host, default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8877, help="Bind port, default: 8877")
    return parser.parse_args()


def _port_is_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def main() -> None:
    args = parse_args()
    import uvicorn

    if not _port_is_available(args.host, args.port):
        print(
            f"CosyVoice TTS service already appears to be running at http://{args.host}:{args.port}. "
            "Reuse the existing service, or stop it before starting a new one.",
            file=sys.stderr,
        )
        raise SystemExit(0)

    uvicorn.run("tts_service:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

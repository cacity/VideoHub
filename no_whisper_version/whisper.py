"""
轻量版 stub: 替代真实的 `whisper` 库，用于“无音频转字幕”版本。

注意：
- 只实现了项目中用到的最小接口：`load_model(...).transcribe(...)`
- `transcribe` 不做真正的语音识别，只返回一个空结果，并打印提示。
"""

from typing import Any, Dict


class _ModelStub:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.model_name = kwargs.get("name") or (args[0] if args else "unknown")

    def transcribe(self, audio_path: str, **kwargs: Any) -> Dict[str, Any]:
        """
        不执行真实转录，只返回空结果，避免程序报错。
        """
        print(
            f"[whisper stub] 当前为无音频版构建，已跳过 Whisper 转录：{audio_path}"
        )
        # 返回一个结构兼容的空结果，避免后续代码崩溃
        return {
            "text": "",
            "segments": [],
            "language": kwargs.get("language", "en"),
        }


def load_model(model_size: str = "small", device: str | None = None) -> _ModelStub:
    """
    替代 `whisper.load_model`，返回一个 stub 模型。
    """
    print(
        f"[whisper stub] 已加载轻量 stub 模型（不包含真实 Whisper 功能）："
        f"model={model_size}, device={device or 'cpu'}"
    )
    return _ModelStub(model_size=model_size, device=device)


__all__ = ["load_model"]


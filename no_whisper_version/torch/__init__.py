"""
轻量版 stub: 替代真实的 `torch` 库，用于“无音频转字幕”版本。

只实现项目中用到的极少部分：
- torch.cuda.is_available()
- torch.cuda.empty_cache()
- torch.cuda.device_count()
- torch.cuda.get_device_name()
- torch.cuda.get_device_properties().total_memory
- torch.cuda.set_per_process_memory_fraction()
- torch.set_num_threads()
"""

from types import SimpleNamespace


class _CudaStub:
    @staticmethod
    def is_available() -> bool:
        # 在轻量版中统一视为不可用，避免触发 GPU 相关逻辑
        return False

    @staticmethod
    def empty_cache() -> None:
        # 不需要做任何事情
        pass

    @staticmethod
    def device_count() -> int:
        return 0

    @staticmethod
    def get_device_name(index: int) -> str:
        return "No GPU (torch stub)"

    @staticmethod
    def get_device_properties(index: int):
        # 只提供 total_memory 字段
        return SimpleNamespace(total_memory=0)

    @staticmethod
    def set_per_process_memory_fraction(fraction: float) -> None:
        # 仅为兼容接口
        pass


class _VersionStub:
    # 提供一个伪造的 CUDA 版本字符串
    cuda: str = "0.0 (stub)"


cuda = _CudaStub()
version = _VersionStub()


def set_num_threads(n: int) -> None:
    # 在 stub 中不做任何处理，只为兼容接口
    pass


__all__ = ["cuda", "version", "set_num_threads"]


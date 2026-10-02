"""Resource controls for local Whisper transcription workloads."""

from __future__ import annotations

import ctypes
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Mapping, Optional


@dataclass(frozen=True)
class WhisperResourcePolicy:
    profile: str
    device_preference: str
    logical_cpu_count: int
    cpu_threads: int
    gpu_memory_fraction: float
    process_priority: str


_PROFILE_DEFAULTS = {
    "eco": {
        "cpu_ratio": 0.30,
        "gpu_memory_fraction": 0.40,
        "process_priority": "idle",
    },
    "balanced": {
        "cpu_ratio": 0.50,
        "gpu_memory_fraction": 0.60,
        "process_priority": "below_normal",
    },
    "performance": {
        "cpu_ratio": 0.80,
        "gpu_memory_fraction": 0.85,
        "process_priority": "normal",
    },
}

_VALID_DEVICES = {"auto", "cpu", "cuda"}
_VALID_PRIORITIES = {"idle", "below_normal", "normal"}
_WHISPER_EXECUTION_LOCK = threading.Lock()


def _read_int(value: Optional[str], default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def resolve_whisper_resource_policy(
    environ: Optional[Mapping[str, str]] = None,
    cpu_count: Optional[int] = None,
) -> WhisperResourcePolicy:
    """Resolve the effective policy from environment variables.

    A value of 0 for ``WHISPER_CPU_THREADS`` or
    ``WHISPER_GPU_MEMORY_PERCENT`` means to use the selected profile default.
    """

    env = environ if environ is not None else os.environ
    profile = str(env.get("WHISPER_RESOURCE_PROFILE", "balanced")).strip().lower()
    if profile not in _PROFILE_DEFAULTS:
        profile = "balanced"

    defaults = _PROFILE_DEFAULTS[profile]
    logical_cpu_count = max(1, int(cpu_count or os.cpu_count() or 1))
    reserve = 2 if logical_cpu_count >= 6 else (1 if logical_cpu_count > 1 else 0)
    usable_cpu_count = max(1, logical_cpu_count - reserve)
    automatic_threads = max(
        1,
        min(usable_cpu_count, round(logical_cpu_count * defaults["cpu_ratio"])),
    )
    requested_threads = _read_int(env.get("WHISPER_CPU_THREADS"), 0)
    cpu_threads = (
        max(1, min(logical_cpu_count, requested_threads))
        if requested_threads > 0
        else automatic_threads
    )

    requested_gpu_percent = _read_int(env.get("WHISPER_GPU_MEMORY_PERCENT"), 0)
    gpu_memory_fraction = (
        max(0.20, min(0.95, requested_gpu_percent / 100.0))
        if requested_gpu_percent > 0
        else float(defaults["gpu_memory_fraction"])
    )

    device_preference = str(env.get("WHISPER_DEVICE", "auto")).strip().lower()
    if device_preference not in _VALID_DEVICES:
        device_preference = "auto"

    process_priority = str(
        env.get("WHISPER_PROCESS_PRIORITY", defaults["process_priority"])
    ).strip().lower()
    if process_priority not in _VALID_PRIORITIES:
        process_priority = str(defaults["process_priority"])

    return WhisperResourcePolicy(
        profile=profile,
        device_preference=device_preference,
        logical_cpu_count=logical_cpu_count,
        cpu_threads=cpu_threads,
        gpu_memory_fraction=gpu_memory_fraction,
        process_priority=process_priority,
    )


def apply_process_priority(priority: str) -> bool:
    """Lower this process' scheduler priority so foreground apps stay responsive."""

    if priority not in _VALID_PRIORITIES:
        return False

    try:
        if os.name == "nt":
            priority_classes = {
                "idle": 0x00000040,
                "below_normal": 0x00004000,
                "normal": 0x00000020,
            }
            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.SetPriorityClass.restype = ctypes.c_int
            process = kernel32.GetCurrentProcess()
            if not kernel32.SetPriorityClass(process, priority_classes[priority]):
                raise ctypes.WinError()
        else:
            # POSIX can safely lower priority without privileges. Do not try to
            # raise it again, which would normally require elevated privileges.
            nice_targets = {"idle": 10, "below_normal": 5, "normal": 0}
            target = nice_targets[priority]
            current = os.nice(0)
            if target > current:
                os.nice(target - current)
        return True
    except (AttributeError, OSError):
        return False


@contextmanager
def temporary_process_priority(priority: str):
    """Apply a lower Windows process priority only while Whisper is running."""

    if os.name != "nt":
        yield
        return

    previous_priority = None
    kernel32 = None
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        kernel32.GetPriorityClass.restype = ctypes.c_uint32
        previous_priority = kernel32.GetPriorityClass(
            kernel32.GetCurrentProcess()
        )
    except (AttributeError, OSError):
        previous_priority = None

    apply_process_priority(priority)
    try:
        yield
    finally:
        if kernel32 is not None and previous_priority:
            try:
                kernel32.SetPriorityClass(
                    kernel32.GetCurrentProcess(), previous_priority
                )
            except (AttributeError, OSError):
                pass


def apply_whisper_resource_policy(
    torch_module,
    policy: Optional[WhisperResourcePolicy] = None,
    logger: Callable[[str], None] = print,
) -> str:
    """Apply CPU, process-priority and GPU-memory controls to PyTorch."""

    active_policy = policy or resolve_whisper_resource_policy()
    thread_count = str(active_policy.cpu_threads)
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        os.environ[key] = thread_count

    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["CUDA_LAUNCH_BLOCKING"] = "0"

    torch_module.set_num_threads(active_policy.cpu_threads)
    try:
        torch_module.set_num_interop_threads(
            max(1, min(2, active_policy.cpu_threads))
        )
    except RuntimeError:
        # PyTorch only permits changing this before inter-op work starts.
        pass

    cuda_available = bool(torch_module.cuda.is_available())
    if active_policy.device_preference == "cpu":
        device = "cpu"
    elif active_policy.device_preference == "cuda":
        device = "cuda" if cuda_available else "cpu"
        if not cuda_available:
            logger("Whisper requested CUDA, but CUDA is unavailable; falling back to CPU.")
    else:
        device = "cuda" if cuda_available else "cpu"

    if device == "cuda":
        torch_module.cuda.empty_cache()
        try:
            torch_module.cuda.set_per_process_memory_fraction(
                active_policy.gpu_memory_fraction
            )
        except (AttributeError, AssertionError, RuntimeError):
            logger("GPU memory limiting is not supported by this PyTorch build.")

    logger(
        "Whisper resource policy: "
        f"profile={active_policy.profile}, device={device}, "
        f"CPU threads={active_policy.cpu_threads}/{active_policy.logical_cpu_count}, "
        f"GPU memory cap={active_policy.gpu_memory_fraction:.0%}, "
        f"priority={active_policy.process_priority} during transcription"
    )
    return device


@contextmanager
def whisper_execution_slot(logger: Callable[[str], None] = print):
    """Serialize Whisper model execution to prevent stacked CPU/GPU loads."""

    acquired_immediately = _WHISPER_EXECUTION_LOCK.acquire(blocking=False)
    if not acquired_immediately:
        logger("Another Whisper transcription is running; waiting for its resource slot.")
        _WHISPER_EXECUTION_LOCK.acquire()
    try:
        policy = resolve_whisper_resource_policy()
        with temporary_process_priority(policy.process_priority):
            yield
    finally:
        _WHISPER_EXECUTION_LOCK.release()

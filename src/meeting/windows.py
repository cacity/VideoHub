"""Windows capture boundaries: screen coordinates and uninterrupted PCM input."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


def dpi_aware():
    if os.name == 'nt':
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass


def monitors():
    if os.name != 'nt':
        raise ValueError('会议录屏首版仅支持Windows')
    user = ctypes.windll.user32
    result = []
    class Info(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT), ('work', wintypes.RECT),
                    ('flags', wintypes.DWORD), ('device', wintypes.WCHAR * 32)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def visit(handle, dc, rect, data):
        info = Info()
        info.size = ctypes.sizeof(info)
        if user.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.monitor
            result.append({'name': info.device, 'x': r.left, 'y': r.top,
                           'width': r.right - r.left, 'height': r.bottom - r.top})
        return True
    user.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(Info)]
    callback = callback_type(visit)
    user.EnumDisplayMonitors(None, None, callback, 0)
    return result


def exclude_window(widget) -> bool:
    """Use Windows capture exclusion, checking the actual affinity value."""
    if os.name != 'nt':
        return False
    hwnd = wintypes.HWND(int(widget.winId()))
    user = ctypes.windll.user32
    affinity = wintypes.DWORD()
    return bool(user.SetWindowDisplayAffinity(hwnd, 0x11)
                and user.GetWindowDisplayAffinity(hwnd, ctypes.byref(affinity)) and affinity.value == 0x11)


def audio_capture(device, stop, deliver, ready):
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        info = audio.get_device_info_by_index(device)
        if not info.get('isLoopbackDevice'):
            raise ValueError('请选择播放设备的回环声音')
        rate, channels = int(info['defaultSampleRate']), int(info['maxInputChannels'])
        with audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                        input_device_index=device, frames_per_buffer=rate // 10) as stream:
            ready(rate, channels)
            while not stop.is_set():
                # Overflow is a recording error, never silently drop original audio.
                raw = stream.read(rate // 10, exception_on_overflow=True)
                if stop.is_set():
                    break
                deliver(raw, time.time() - (len(raw) / (channels * 2 * rate)))


def region_for(screen, x=0, y=0, width=None, height=None):
    width = screen['width'] if width is None else width
    height = screen['height'] if height is None else height
    values = [x, y, width, height]
    if any(type(v) is not int for v in values) or min(x, y) < 0 or min(width, height) < 128:
        raise ValueError('录制区域至少128×128像素，偏移不能为负')
    if x + width > screen['width'] or y + height > screen['height']:
        raise ValueError('录制区域超出所选屏幕')
    return {'x': screen['x'] + x, 'y': screen['y'] + y, 'width': width // 2 * 2, 'height': height // 2 * 2}

"""Concise download errors without signed URLs or F2 request parameters."""

from contextlib import contextmanager
from contextvars import ContextVar
import logging
import re
from urllib.parse import parse_qs, urlsplit


_f2_call = ContextVar("videohub_f2_call", default=False)
_f2_quiet = ContextVar("videohub_f2_quiet", default=False)


def work_label(url, info=None):
    """Identify the work without logging full URLs or making another request."""
    info = info or {}
    work_id = str(info.get("aweme_id") or "")
    try:
        parsed = urlsplit(url)
    except ValueError:
        parsed = urlsplit("")
    if not work_id or work_id == "unknown":
        match = re.search(r"/(?:share/)?video/(\d+)", parsed.path)
        work_id = match[1] if match else parse_qs(parsed.query).get("modal_id", [""])[0]
    if work_id.isdigit():
        identity = f"作品ID {work_id}"
    elif parsed.hostname == "v.douyin.com" and re.fullmatch(r"[A-Za-z0-9_-]{3,80}", parsed.path.strip("/")):
        identity = f"分享码 {parsed.path.strip('/')}"
    else:
        identity = "当前抖音作品"
    title = " ".join(str(info.get("desc") or "").split())[:60]
    return f"{title}（{identity}）" if title else identity


def provider_label(name):
    return {"f2": "F2", "dlpanda": "DLPanda"}.get(name, name or "未知来源")


def report_status(message, callback=None, progress=0):
    if callback:
        callback(message, progress)
    else:
        print(message)


def http_status(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    match = re.search(
        r"(?:HTTP(?:状态(?:码)?(?:错误)?)?|Status Code|Client error|Server error)\s*[:：'\" ]*([45]\d\d)\b",
        str(error), re.I,
    )
    return int(match[1]) if match else None


def concise_error(error) -> str:
    status = http_status(error)
    if status:
        reason = {
            401: "服务器要求有效授权", 403: "服务器拒绝访问",
            404: "资源不存在或地址已失效", 410: "地址已失效",
            429: "请求过于频繁，请稍后重试",
        }.get(status, "服务器请求失败")
        return f"HTTP {status}：{reason}"
    message = re.sub(r"https?://[^\s<>\"']+", "[地址已省略]", str(error))
    return " ".join(message.split())[:400] or type(error).__name__


class _F2LogFilter(logging.Filter):
    def filter(self, record):
        if _f2_call.get():
            if _f2_quiet.get():
                return False
            message = concise_error(record.getMessage())
            if record.exc_info:
                message += "；" + concise_error(record.exc_info[1])
            record.msg, record.args = message, ()
            record.exc_info = record.exc_text = record.stack_info = None
        return True


_f2_filter = _F2LogFilter()


@contextmanager
def concise_f2_logs(*, quiet=False):
    # Keep F2's levels and handlers. Only sanitize/suppress records for this
    # call; unrelated calls and concurrent work retain their logging behavior.
    logging.getLogger("f2").addFilter(_f2_filter)
    token = _f2_call.set(True)
    quiet_token = _f2_quiet.set(quiet)
    try:
        yield
    finally:
        _f2_quiet.reset(quiet_token)
        _f2_call.reset(token)

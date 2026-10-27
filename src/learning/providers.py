"""Small provider boundary: no secrets in responses, no hidden paid fallbacks."""

from __future__ import annotations

import json
import os
import re
import threading
from urllib.parse import urlsplit

import requests


class Provider:
    def __init__(self, name: str = "deepseek", model: str = ""):
        if name not in {"deepseek", "kimi"}:
            raise ValueError("支持 DeepSeek 或 Kimi")
        self.name = name
        prefix = "DEEPSEEK" if name == "deepseek" else "MOONSHOT"
        self.key = os.getenv(prefix + "_API_KEY", "").strip()
        if name == "kimi":
            self.key = self.key or os.getenv("KIMI_API_KEY", "").strip()
        self.base = os.getenv(
            prefix + "_BASE_URL", "https://api.deepseek.com" if name == "deepseek" else "https://api.moonshot.cn/v1"
        ).rstrip("/")
        parsed = urlsplit(self.base)
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
            raise ValueError("模型服务必须使用 HTTPS 或本机地址")
        self.model = (
            model.strip()
            or os.getenv(prefix + "_MODEL", "").strip()
            or ("deepseek-flash" if name == "deepseek" else "kimi-k2.6")
        )
        if len(self.model) > 120 or not re.fullmatch(r"[A-Za-z0-9_./:-]+", self.model):
            raise ValueError("模型名称无效")
        # Conservative byte budget is an upper bound on typical byte-pair token counts.
        try:
            self.budget = min(100_000, max(6000, int(os.getenv("LEARNING_INPUT_BUDGET", "24000"))))
        except ValueError:
            self.budget = 24000

    def require_key(self):
        if not self.key:
            raise ValueError(
                "未配置 "
                + ("DEEPSEEK_API_KEY" if self.name == "deepseek" else "MOONSHOT_API_KEY / KIMI_API_KEY")
                + "，请在本机 .env 中配置后重启学习服务"
            )

    def stream(self, messages: list[dict], cancelled: threading.Event, max_tokens: int = 2200):
        self.require_key()
        if sum(len(m["content"].encode("utf-8")) + 32 for m in messages) > self.budget:
            raise ValueError("本次上下文超过配置预算，请缩小选段或提高 LEARNING_INPUT_BUDGET")
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
            "stream_options": {"include_usage": True},
        }
        if self.name == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        if self.name == "kimi" and "k2.6" in self.model:
            payload["thinking"] = {"type": "disabled"}
        if cancelled.is_set():
            raise InterruptedError()
        try:
            with requests.post(
                self.base + "/chat/completions",
                headers={"Authorization": "Bearer " + self.key},
                json=payload,
                stream=True,
                timeout=(10, 60),
            ) as response:
                if response.status_code != 200:
                    raise ValueError(provider_error(self.name, response.status_code))
                response.encoding = "utf-8"
                finish, received = None, False
                for line in response.iter_lines(chunk_size=1, decode_unicode=True):
                    if cancelled.is_set():
                        raise InterruptedError()
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        raise ValueError("模型返回了无法解析的数据流") from None
                    if data.get("error"):
                        raise ValueError("模型服务在回复过程中返回错误，请稍后重试")
                    if data.get("usage"):
                        yield {"usage": data["usage"]}
                    for choice in data.get("choices", []):
                        content = choice.get("delta", {}).get("content")
                        if content:
                            received = True
                            yield {"text": content}
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
                if finish != "stop":
                    raise ValueError(
                        "模型回复未完整结束" + ("（达到输出长度限制）" if finish == "length" else "，请重试")
                    )
                if not received:
                    raise ValueError("模型未返回正文，请检查模型配置")
        except requests.RequestException:
            if cancelled.is_set():
                raise InterruptedError() from None
            raise ValueError("模型服务连接失败或超时，请检查网络后重试") from None

    def complete(self, messages, cancelled, max_tokens=1200) -> tuple[str, dict | None]:
        text, usage = "", None
        for event in self.stream(messages, cancelled, max_tokens):
            text += event.get("text", "")
            usage = event.get("usage", usage)
        return text, usage


def provider_error(name: str, status: int) -> str:
    label = "DeepSeek" if name == "deepseek" else "Kimi"
    detail = {
        400: "请求参数或模型名称不被支持",
        401: "密钥无效",
        402: "余额不足",
        403: "账户无此接口权限",
        404: "模型或接口不存在",
        429: "触发限流，请稍后重试",
    }.get(status, "服务暂不可用")
    return f"{label}：{detail}（HTTP {status}）"


def json_result(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("模型未返回有效的结构化结果，请重试") from None


def capabilities() -> dict:
    result = {}
    for name in ("deepseek", "kimi"):
        try:
            provider = Provider(name)
        except ValueError as error:
            result[name] = {"configured": False, "model": "", "input_budget": 24000, "error": str(error)}
            continue
        result[name] = {"configured": bool(provider.key), "model": provider.model, "input_budget": provider.budget}
    return result

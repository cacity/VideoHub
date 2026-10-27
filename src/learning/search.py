"""Independent, bounded search adapters for the official DeepSeek/Kimi REST APIs."""

from __future__ import annotations

from urllib.parse import urlsplit

import requests

from .notes import safe_url
from .providers import Provider, provider_error
from .store import now


def search_web(name: str, query: str, cancelled) -> list[dict]:
    if not query.strip() or len(query) > 128:
        raise ValueError("搜索词须为 1–128 字")
    provider = Provider(name)
    provider.require_key()
    if cancelled.is_set():
        raise InterruptedError()
    base = provider.base if provider.base.endswith("/v1") else provider.base + "/v1"
    if name == "deepseek":
        endpoint = "/tools/search"
        payload = {"query": query, "count": 5, "need_content": True}
    else:
        endpoint = "/tools/search_pro"
        payload = {"text_query": query, "limit": 5, "timeout_seconds": 25}
    try:
        with requests.post(
            base + endpoint, headers={"Authorization": "Bearer " + provider.key}, json=payload, timeout=(10, 35)
        ) as response:
            if cancelled.is_set():
                raise InterruptedError()
            if response.status_code != 200:
                raise ValueError("联网失败：" + provider_error(name, response.status_code))
            data = response.json()
    except (requests.RequestException, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("联网失败："):
            raise
        raise ValueError("联网搜索连接失败或返回格式无效") from None
    rows = data.get("results" if name == "deepseek" else "search_results")
    if not isinstance(rows, list):
        raise ValueError("搜索接口返回结构不匹配，请检查服务版本")
    result, seen = [], set()
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        url = safe_url(str(row.get("url", "")))
        if not url or url in seen:
            continue
        seen.add(url)
        content = str(row.get("content") or "")
        if not content and isinstance(row.get("chunks"), list):
            content = "\n".join(str(c.get("text", "")) for c in row["chunks"] if isinstance(c, dict))
        level = ("正文片段" if name == "kimi" else "网页正文") if content else "搜索摘要"
        content = content or str(row.get("summary") or row.get("snippet") or "")
        result.append(
            {
                "id": "W" + str(len(result) + 1),
                "url": url,
                "title": str(row.get("title") or urlsplit(url).hostname)[:180],
                "content": content.encode("utf-8")[:650].decode("utf-8", errors="ignore"),
                "level": level,
                "retrieved": now(),
                "provider": name,
                "date": row.get("date"),
            }
        )
    return result

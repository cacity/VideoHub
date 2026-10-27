"""Timestamped notes with source snapshots, optimistic editing and Markdown export."""

from __future__ import annotations

import html
import re
from urllib.parse import quote, urlsplit

from .service import finite
from .store import encode, new_id, now
from .subtitles import timestamp


class NoteConflict(ValueError):
    pass


def safe_url(value: str) -> str:
    parsed = urlsplit(value)
    return value if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username else ""


def save_note(service, video_id: str, data: dict, note_id: str | None = None) -> dict:
    video = service.detail(video_id)
    existing = next((n for n in service.store.list_items("notes", video_id) if n["id"] == note_id), None)
    if note_id and existing is None:
        raise KeyError("笔记不存在")
    if existing and data.get("version") != existing["version"]:
        raise NoteConflict("笔记已在另一个页面修改，请刷新后再编辑")
    start = min(video["duration"], max(0, finite(data.get("start", existing["start"] if existing else 0))))
    end = min(video["duration"], max(start, finite(data.get("end", start))))
    text = str(data.get("text", existing["text"] if existing else "")).strip()
    citations, sources = (existing["citations"], existing["sources"]) if existing else ([], [])
    subtitle_version = existing["subtitle_version"] if existing else video["subtitle_version"]
    if not existing and data.get("answer_id"):
        message = next(
            (
                m
                for m in service.store.list_items("messages", video_id)
                if m["id"] == data["answer_id"] and m["role"] == "assistant"
            ),
            None,
        )
        if not message or message["status"] != "finished":
            raise ValueError("只能收藏当前视频中已经完成的 AI 回答")
        text = text or message["text"]
        citations, sources = message.get("citations", []), message.get("sources", [])
        start = message.get("time", start)
        end = start
        subtitle_version = message["subtitle_version"]
    elif not existing and data.get("cue_ids"):
        wanted = data["cue_ids"]
        if not isinstance(wanted, list) or len(wanted) > 30:
            raise ValueError("摘录字幕数量无效")
        by_id = {c["id"]: c for c in video["cues"]}
        if any(c not in by_id for c in wanted):
            raise ValueError("字幕已更新，请重新选择")
        citations = [{k: by_id[c][k] for k in ("id", "start", "end", "text")} for c in wanted]
        text = text or "\n".join(c["text"] for c in citations)
        start, end = min(c["start"] for c in citations), max(c["end"] for c in citations)
    if not text or len(text) > 30_000:
        raise ValueError("笔记不能为空，最多 30000 字")
    tags = data.get("tags", existing.get("tags", []) if existing else [])
    if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 50 for t in tags):
        raise ValueError("标签格式无效")
    note = {
        "id": note_id or new_id(),
        "text": text,
        "start": start,
        "end": end,
        "created": existing["created"] if existing else now(),
        "updated": now(),
        "version": existing["version"] + 1 if existing else 1,
        "subtitle_version": subtitle_version,
        "citations": citations,
        "sources": sources,
        "tags": tags,
    }
    if existing:
        with service.store.connect() as db:
            changed = db.execute(
                "UPDATE notes SET data=? WHERE id=? AND video_id=? AND data=?",
                (encode(note), note_id, video_id, encode(existing)),
            ).rowcount
            if not changed:
                raise NoteConflict("笔记已改变，请刷新后再编辑")
    else:
        service.store.save_item("notes", video_id, note)
    return note


def markdown(service, video_id: str, origin: str) -> str:
    video = service.store.video(video_id)
    lines = [
        "# " + html.escape(video["title"]),
        "",
        "来源视频：" + (safe_url(video.get("source_url", "")) or "本地文件"),
        "",
        "时间链接需要本机 VideoHub 学习服务运行；字幕摘录保留创建时的版本。",
        "",
    ]
    for note in service.store.list_items("notes", video_id):

        def note_text():
            result = []
            cue_map = {cue["id"]: cue for cue in note["citations"]}
            source_map = {source["id"]: source for source in note["sources"]}
            for part in re.split(r"(\[cue:[^\]]+\]|\[web:[^\]]+\])", note["text"]):
                match = re.fullmatch(r"\[(cue|web):([^\]]+)\]", part)
                if match and match[1] == "cue" and match[2] in cue_map:
                    cue = cue_map[match[2]]
                    result.append(f"[{timestamp(cue['start'])}]({origin}/learn?video={video_id}&t={cue['start']:.3f})")
                elif match and match[1] == "web" and match[2] in source_map and safe_url(source_map[match[2]]["url"]):
                    result.append(f"[网页来源]({quote(source_map[match[2]]['url'], safe=':/?=&%#')})")
                else:
                    result.append(html.escape(part).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]"))
            return "".join(result)

        lines.extend(
            [
                f"## [{timestamp(note['start'])}]({origin}/learn?video={video_id}&t={note['start']:.3f})",
                "",
                note_text(),
                "",
            ]
        )
        for cue in note["citations"]:
            lines.extend(
                [
                    f"> {timestamp(cue['start'])}–{timestamp(cue['end'])} "
                    + html.escape(cue["text"]).replace("\n", "\n> "),
                    "",
                ]
            )
        for source in note["sources"]:
            url = safe_url(source["url"])
            title = html.escape(source["title"]).replace("[", "\\[").replace("]", "\\]")
            if url:
                lines.append(
                    f"- [{title}]({quote(url, safe=':/?=&%#')})（{source.get('level', '外部资料')}，检索于 {source.get('retrieved', '')}）"
                )
        if note["tags"]:
            lines.extend(["", "标签：" + "、".join(html.escape(t) for t in note["tags"])])
        lines.extend(["", "记录于 " + note["created"], ""])
    return "\n".join(lines)

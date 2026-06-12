from __future__ import annotations
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import yt_dlp

ALLOWED_YOUTUBE_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
)
SUPPORTED_FORMATS = frozenset({"SRT", "VTT", "TXT"})
LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

DEFAULT_DATA_DIR = Path(os.getenv("VIDEOHUB_SITE_DATA_DIR", "/opt/videohub-site/data/subtitles"))
DOWNLOAD_SEMAPHORE = threading.Semaphore(int(os.getenv("VIDEOHUB_MAX_DOWNLOADS", "2")))
FILE_TTL_SECONDS = int(os.getenv("VIDEOHUB_SUBTITLE_TTL_SECONDS", "86400"))


class SubtitleServiceError(Exception):
    status_code = 500


class ValidationError(SubtitleServiceError):
    status_code = 400


class NotFoundError(SubtitleServiceError):
    status_code = 404


class UpstreamError(SubtitleServiceError):
    status_code = 502


@dataclass
class SubtitleService:
    data_dir: Path = DEFAULT_DATA_DIR

    def __post_init__(self):
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def inspect(self, url: str) -> dict[str, Any]:
        normalized_url = validate_youtube_url(url)
        info = extract_info(normalized_url)

        subtitles = info.get("subtitles") or {}
        auto_subtitles = info.get("automatic_captions") or {}

        manual_languages = sorted(subtitles.keys())
        auto_languages = sorted(auto_subtitles.keys())

        best_manual = pick_best_manual_language(manual_languages)
        best_auto = pick_best_auto_language(auto_languages)
        best_language = best_manual or best_auto

        return {
            "title": info.get("title", "Unknown"),
            "normalized_url": normalized_url,
            "manual_languages": manual_languages,
            "auto_languages": auto_languages,
            "best_language": best_language,
            "best_is_auto": bool(best_language and not best_manual),
        }

    def download(self, url: str, language: str, output_format: str) -> dict[str, Any]:
        normalized_url = validate_youtube_url(url)
        requested_format = validate_format(output_format)
        selected_language = validate_language(language) if language else None

        cleanup_old_files(self.data_dir, FILE_TTL_SECONDS)

        with DOWNLOAD_SEMAPHORE:
            request_id = uuid.uuid4().hex
            request_dir = safe_join(self.data_dir, request_id)
            request_dir.mkdir(parents=False, exist_ok=False)

            result = self._download_to_dir(
                normalized_url, selected_language, requested_format, request_dir
            )

        return result

    def resolve_file(self, file_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", file_id):
            raise NotFoundError("文件不存在或已过期")

        metadata_path = safe_join(self.data_dir, file_id, "metadata.json")
        if not metadata_path.exists():
            raise NotFoundError("文件不存在或已过期")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        filename = metadata.get("filename")
        if not isinstance(filename, str):
            raise NotFoundError("文件不存在或已过期")

        file_path = safe_join(self.data_dir, file_id, filename)
        if not file_path.is_file():
            raise NotFoundError("文件不存在或已过期")

        return file_path

    def _download_to_dir(
        self, normalized_url: str, language: str, output_format: str, request_dir: Path
    ) -> dict[str, Any]:
        info = extract_info(normalized_url)

        subtitles = info.get("subtitles") or {}
        auto_subtitles = info.get("automatic_captions") or {}

        chosen_language = choose_available_language(language, subtitles, auto_subtitles)

        if not chosen_language:
            raise NotFoundError("该视频没有可用的字幕")

        source_path = download_subtitle_file(normalized_url, chosen_language, request_dir)

        title = sanitize_filename(info.get("title", "youtube-subtitle"))
        final_filename = f"{title}.{chosen_language.lower()}.{output_format.lower()}"
        final_path = safe_join(request_dir, final_filename)

        content = source_path.read_text(encoding="utf-8", errors="replace")
        converted = convert_subtitle_content(content, source_path.suffix.lower(), output_format)
        final_path.write_text(converted, encoding="utf-8")

        # Clean up other files
        for candidate in request_dir.iterdir():
            if candidate.is_file() and candidate.name not in {final_filename, "metadata.json"}:
                candidate.unlink(missing_ok=True)

        metadata = {
            "filename": final_filename,
            "title": info.get("title", "Unknown"),
            "language": chosen_language,
            "format": output_format,
            "created_at": int(time.time()),
        }
        safe_join(request_dir, "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )

        file_id = request_dir.name

        return {
            "id": file_id,
            "title": metadata["title"],
            "filename": final_filename,
            "format": output_format,
            "language": chosen_language,
            "preview": extract_preview(converted, output_format),
            "download_url": f"/api/subtitles/files/{file_id}",
        }


def validate_youtube_url(url: str) -> str:
    raw_url = url.strip() if url else ""
    if not raw_url:
        raise ValidationError("请输入 YouTube 视频链接")

    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("链接必须以 http:// 或 https:// 开头")

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_YOUTUBE_HOSTS:
        raise ValidationError("该链接目前只支持 YouTube 视频")

    if is_youtube_playlist_url(raw_url):
        raise ValidationError("暂不支持播放列表或频道视频链接")

    normalized = normalize_youtube_video_url(raw_url)
    normalized_parsed = urlparse(normalized)
    if (normalized_parsed.hostname or "").lower() not in ALLOWED_YOUTUBE_HOSTS:
        raise ValidationError("YouTube 链接格式不正确")

    return normalized


def validate_format(output_format: str) -> str:
    value = (output_format or "").strip().upper()
    if value not in SUPPORTED_FORMATS:
        raise ValidationError("字幕格式只支持 SRT、VTT、TXT")
    return value


def validate_language(language: str) -> str:
    value = (language or "").strip()
    if value in {"auto", "AUTO", "自动识别"}:
        raise ValidationError("自动识别不应作为语言参数提交")
    if not LANGUAGE_RE.fullmatch(value):
        raise ValidationError("字幕语言代码不正确")
    return value


def is_youtube_playlist_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path or ""

    if path.startswith("/playlist") and "list" in query:
        return True

    if path.startswith("/watch") and "list" in query and "v" not in query:
        return True

    return False


def normalize_youtube_video_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = parse_qs(parsed.query)

    if host.endswith("youtu.be") and path and path != "/":
        video_id = path.strip("/").split("/")[0]
        return f"https://youtu.be/{video_id}"

    if host.endswith("youtube.com") and path.startswith("/watch") and "v" in query:
        return f"https://www.youtube.com/watch?v={query['v'][0]}"

    if host.endswith("youtube.com") and path.startswith("/shorts/"):
        parts = path.split("/")
        if len(parts) > 2:
            video_id = parts[2]
            return f"https://www.youtube.com/watch?v={video_id}"

    return url


def choose_available_language(
    language: str | None, subtitles: dict[str, Any], auto_subtitles: dict[str, Any]
) -> str | None:
    manual_languages = sorted(subtitles.keys())
    auto_languages = sorted(auto_subtitles.keys())

    if not language:
        return pick_best_manual_language(manual_languages) or pick_best_auto_language(auto_languages)

    if language in manual_languages:
        return language

    # Check aliases
    aliases = {
        "zh": ["zh-CN", "zh-Hans", "zh-TW", "zh-Hant"],
        "en": ["en-US", "en-GB", "en-orig"],
    }
    for alias_list in aliases.values():
        if language in alias_list:
            for candidate in alias_list:
                if candidate in manual_languages:
                    return candidate

    if language in auto_languages:
        return language

    for alias_list in aliases.values():
        if language in alias_list:
            for candidate in alias_list:
                if candidate in auto_languages:
                    return candidate

    raise ValidationError("所选语言没有可用的字幕")


def extract_info(url: str) -> dict[str, Any]:
    try:
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        raise UpstreamError(f"获取 YouTube 字幕信息失败: {e}")


def download_subtitle_file(url: str, language: str, output_dir: Path) -> Path:
    path = output_dir.resolve()
    before = set(path.glob("*"))

    opts = {
        "quiet": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [language],
        "subtitlesformat": "srt/vtt",
        "skip_download": True,
        "outtmpl": "%(title).80s.%(ext)s",
        "paths": {"home": str(path)},
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise UpstreamError(f"下载字幕失败: {e}")

    after = set(path.glob("*"))
    candidates = after - before
    subtitle_candidates = [c for c in candidates if c.suffix.lower() in {".srt", ".vtt"}]

    if not subtitle_candidates:
        raise NotFoundError("没有下载到字幕文件")

    return subtitle_candidates[0]


def pick_best_manual_language(languages: list[str]) -> str | None:
    wanted = ("zh-CN", "zh-Hans", "zh", "zh-TW", "zh-Hant", "en", "en-US", "en-GB")
    for lang in wanted:
        if lang in languages:
            return lang
    if languages:
        return languages[0]
    return None


def pick_best_auto_language(languages: list[str]) -> str | None:
    wanted = ("en-orig", "en", "en-US", "en-GB", "zh-CN", "zh-Hans", "zh", "zh-TW", "zh-Hant")
    for lang in wanted:
        if lang in languages:
            return lang
    if languages:
        return languages[0]
    return None


def convert_subtitle_content(content: str, source_extension: str, output_format: str) -> str:
    fmt = validate_format(output_format)
    text = content.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"

    if fmt == "VTT":
        return to_vtt(text, source_extension)
    elif fmt == "SRT":
        return to_srt(text, source_extension)
    else:
        return to_txt(text, source_extension)


def to_vtt(content: str, source_extension: str) -> str:
    if source_extension == ".vtt":
        if content.lstrip().startswith("WEBVTT"):
            return content
        return f"WEBVTT\n\n{content}"

    body = re.sub(r"(?m)^\d+\s*$", "", content)
    body = body.replace(",", ".")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return f"WEBVTT\n\n{body}\n"


def to_srt(content: str, source_extension: str) -> str:
    if source_extension == ".srt" and not content.lstrip().startswith("WEBVTT"):
        return content

    text = re.sub(r"^WEBVTT.*?\n\n", "", content, flags=re.DOTALL)

    if "-->" in text[:80]:
        text = text.replace(".", ",", 1)

    text = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", text)

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    output_blocks = []
    index = 1

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        lines = [l for l in lines if not l.upper().startswith(("NOTE", "STYLE", "REGION"))]

        if not any("-->" in l for l in lines):
            continue

        if lines and re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]

        output_blocks.append("\n".join([str(index)] + lines))
        index += 1

    return "\n\n".join(output_blocks).strip() + "\n"


def to_txt(content: str, source_extension: str) -> str:
    text = re.sub(r"^WEBVTT.*?\n\n", "", content, flags=re.DOTALL)

    lines = []
    for line in text.split("\n"):
        stripped = re.sub(r"<[^>]+>", "", line.strip())
        if not stripped:
            continue
        if stripped.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if "-->" in stripped or re.fullmatch(r"\d+", stripped):
            continue
        if stripped not in lines:
            lines.append(stripped)

    return "\n".join(lines).strip() + "\n"


def extract_preview(content: str, output_format: str, limit: int = 3) -> list[dict]:
    if output_format == "TXT":
        lines = to_txt(content, ".txt").splitlines()[:limit]
        return [{"time": "", "text": line.strip()} for line in lines if line.strip()]

    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", normalized) if b.strip()]

    preview = []
    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        lines = [l for l in lines if not l.upper().startswith(("NOTE", "STYLE", "REGION"))]

        time_line = next((l for l in lines if "-->" in l), None)
        if not time_line:
            continue

        text_lines = [l for l in lines if l != time_line and not re.fullmatch(r"\d+", l)]
        text = re.sub(r"<[^>]+>", "", " ".join(text_lines)).strip()

        if text:
            preview.append({
                "time": time_line.split("-->")[0].strip(),
                "text": text,
            })

        if len(preview) >= limit:
            break

    return preview


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(
        r'[<>:"/\\|?*\[\]{};\'`~!@#$%^&()+=一-鿿\s]+', "_", filename
    )
    cleaned = re.sub(r"_+", "_", cleaned).strip("_. ")
    return cleaned or "youtube-subitle"


def safe_join(base_dir: Path, *parts: str) -> Path:
    base = Path(base_dir).resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise ValidationError("文件路径不安全")
    return target


def cleanup_old_files(data_dir: Path, ttl_seconds: int):
    cutoff = time.time() - ttl_seconds
    for child in Path(data_dir).glob("*"):
        if child.is_dir() and child.stat().st_mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)

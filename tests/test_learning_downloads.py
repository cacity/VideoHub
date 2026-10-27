import json
from pathlib import Path

import pytest

from src.learning import downloads
from src.learning.project import MANIFEST, inspect_project

SRT = "1\n00:00:00,000 --> 00:00:02,000\nHello.\n"
URL = "https://www.youtube.com/watch?v=testvideo01"


def test_bundle_is_portable_idempotent_and_preserves_originals(tmp_path):
    source = tmp_path / "legacy" / "Lesson.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    source.with_suffix(".en.srt").write_text(SRT, encoding="utf-8")
    source.with_suffix(".zh-CN.srt").write_text(SRT.replace("Hello.", "你好。"), encoding="utf-8")
    root = tmp_path / "project"
    result = downloads.bundle_download(source, root, URL)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    assert result.read_bytes() == source.read_bytes()
    assert source.with_suffix(".en.srt").is_file()
    assert len(manifest["subtitles"]) == 2
    assert all(not Path(t["path"]).is_absolute() for t in manifest["subtitles"])
    assert manifest["source_url"] == URL
    downloads.bundle_download(source, root, URL)
    assert json.loads((root / MANIFEST).read_text(encoding="utf-8"))["id"] == manifest["id"]
    source.write_bytes(b"a different video")
    with pytest.raises(ValueError, match="同名"):
        downloads.bundle_download(source, root, URL)
    assert result.read_bytes() == b"video"


@pytest.mark.parametrize("route", ["download_only", "manual", "manual_subtitles", "auto", "whisper", "reuse", "failed_transcription"])
def test_online_download_routes_keep_every_asset_in_project(tmp_path, monkeypatch, route):
    from src import youtube_transcriber as yt

    root = tmp_path / "project"
    monkeypatch.setattr(downloads, "project_directory", lambda url: root)
    monkeypatch.setattr(downloads, "update_history", lambda *args: None)
    monkeypatch.setattr(yt, "check_cookies_file", lambda path: None)
    monkeypatch.setattr(yt, "log_downloaded_video", lambda *args: None)
    captured = {}

    def download(url, output_dir, audio_only=False, **kwargs):
        output = Path(output_dir) / ("Lesson.mp3" if audio_only else "Lesson.mp4")
        if route == "reuse" and not audio_only:
            output = tmp_path / "legacy" / "Lesson.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix(".en.srt").write_text(SRT, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"media")
        return str(output)

    def native(url, output_dir, **kwargs):
        output = Path(output_dir) / "Lesson.en.srt"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(SRT, encoding="utf-8")
        return [str(output)]

    def translate(path, output_dir, **kwargs):
        output = Path(output_dir) / "Lesson.zh-CN.srt"
        output.write_text(SRT.replace("Hello.", "你好。"), encoding="utf-8")
        return str(output)

    def transcribe(path, output_dir, subtitle_dir, **kwargs):
        assert Path(path).is_relative_to(root)
        captured["transcript"] = Path(output_dir)
        captured["subtitles"] = Path(subtitle_dir)
        if route == "failed_transcription":
            raise ValueError("simulated transcription failure")
        text = Path(output_dir) / "Lesson.txt"
        text.parent.mkdir(parents=True, exist_ok=True)
        text.write_text("Hello.", encoding="utf-8")
        return str(text), native(URL, subtitle_dir)[0]

    def summary(*args, **kwargs):
        directory = Path(kwargs.get("output_dir") or args[5])
        captured["summary"] = directory
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / "Lesson.md"
        output.write_text("Summary.", encoding="utf-8")
        return str(output)

    monkeypatch.setattr(yt, "download_youtube_video", download)
    monkeypatch.setattr(yt, "extract_audio_from_video", lambda path, output_dir: download(URL, output_dir, True))
    monkeypatch.setattr(
        yt,
        "check_youtube_subtitles",
        lambda *args: {
            "has_manual_subtitles": route in {"manual", "manual_subtitles"},
            "has_auto_subtitles": route == "auto",
            "manual_languages": ["en"],
            "auto_languages": ["en"],
            "best_manual_language": "en",
            "best_auto_language": "en",
        },
    )
    monkeypatch.setattr(yt, "download_youtube_subtitles", native)
    monkeypatch.setattr(yt, "translate_subtitle_file", translate)
    monkeypatch.setattr(yt, "convert_subtitle_to_text", lambda path: "Hello.")
    monkeypatch.setattr(yt, "transcribe_audio_unified", transcribe)
    monkeypatch.setattr(yt, "summarize_text", summary)
    result = yt.process_youtube_video(
        URL,
        download_video=True,
        generate_subtitles=route != "download_only",
        generate_article=route not in {"download_only", "manual_subtitles"},
        enable_transcription=route != "download_only",
        translate_to_chinese=route != "download_only",
        prefer_native_subtitles=route in {"manual", "manual_subtitles", "auto"},
    )
    assert bool(result) == (route != "failed_transcription")
    project = inspect_project(str(root))
    assert project["id"]
    assert Path(project["path"]).parent == root
    assert all(Path(t["path"]).is_relative_to(root) for t in project["tracks"])
    assert all(p.is_relative_to(root) for p in captured.values())
    if route == "download_only":
        assert not (root / "audio").exists()
    elif route != "failed_transcription":
        assert project["tracks"]
        if route != "manual_subtitles":
            assert captured["summary"] == root / "summaries"

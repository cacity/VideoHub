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


@pytest.mark.parametrize("route", ["subtitles", "summary", "failed_transcription"])
def test_douyin_download_and_processing_stay_in_learning_project(tmp_path, monkeypatch, route):
    from src import youtube_transcriber as yt
    from douyin.config import DouyinConfig
    from douyin.downloader import DouyinDownloader

    base = tmp_path / "learning" / "projects"
    project_directory = downloads.project_directory
    monkeypatch.setattr(downloads, "recent_downloads", lambda: [])
    monkeypatch.setattr(downloads, "project_directory", lambda url: project_directory(url, base))
    history = []
    monkeypatch.setattr(yt, "log_downloaded_video", lambda *args: history.append(args))
    legacy = tmp_path / "douyin"
    downloader = DouyinDownloader(DouyinConfig({"download_dir": str(legacy), "download_cover": False}))
    media_requests = []

    def media(url, output_path, *args):
        if not output_path.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(url.encode())
            media_requests.append(url)
        return output_path

    monkeypatch.setattr(downloader.douyinvd_extractor, "_download_media", media)
    roots = []
    for work_id in ["7660369906369629476", "7660369906369629477"]:
        info = {"aweme_id": work_id, "desc": "完全相同的系列标题", "provider": "f2",
                "video": {"play_url": "https://cdn.example/" + work_id}}
        source_url = "https://v.douyin.com/share-" + work_id + "/"
        result = downloads.download_douyin(downloader, source_url, video_info=info)
        assert result["success"], result
        root = Path(result["project_root"])
        roots.append(root)
        assert root == base / ("douyin_" + work_id)
        video = Path(result["files"]["video"][0])
        original_id = inspect_project(str(root))["id"]

        def extract(path, output_dir):
            assert Path(path) == video
            output = Path(output_dir) / (video.stem + ".mp3")
            output.write_bytes(b"audio")
            return str(output)

        def transcribe(path, output_dir, subtitle_dir, **kwargs):
            assert Path(path).is_relative_to(root / "audio")
            if route == "failed_transcription":
                raise ValueError("transcription failed")
            assert kwargs["generate_subtitles"] and kwargs["translate_to_chinese"]
            text = Path(output_dir) / (video.stem + ".txt")
            text.write_text("Hello.", encoding="utf-8")
            source = Path(subtitle_dir) / (video.stem + ".en.srt")
            source.write_text(SRT, encoding="utf-8")
            target = source.with_name(video.stem + ".zh-CN.srt")
            target.write_text(SRT.replace("Hello.", "你好。"), encoding="utf-8")
            return str(text), str(target)

        def summary(path, output_dir, **kwargs):
            assert Path(path).is_relative_to(root / "transcripts")
            output = Path(output_dir) / (video.stem + ".md")
            output.write_text("Summary.", encoding="utf-8")
            return str(output)

        monkeypatch.setattr(yt, "extract_audio_from_video", extract)
        monkeypatch.setattr(yt, "transcribe_audio_unified", transcribe)
        monkeypatch.setattr(yt, "summarize_text", summary)
        processed = yt.process_local_video(str(video), generate_subtitles=True, generate_article=route == "summary")
        assert bool(processed) == (route != "failed_transcription")
        if processed:
            assert Path(processed).is_relative_to(root)
        project = inspect_project(str(root))
        assert project["id"] == original_id
        assert len(project["tracks"]) == (0 if route == "failed_transcription" else 2)
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        assert manifest["source_url"] == source_url
        assert len(manifest["subtitles"]) == len(project["tracks"])
        # Another share link for the same work reuses media and learning ID.
        again = downloads.download_douyin(downloader, source_url + "?new-share=1", video_info=info)
        assert again["project_root"] == str(root)
        assert inspect_project(str(root))["id"] == original_id
    assert roots[0] != roots[1]
    assert len(media_requests) == 2
    assert not list(legacy.iterdir())
    assert all(Path(item[1]).is_relative_to(base) for item in history)
    assert downloader.config.get("download_dir") == str(legacy)


def test_douyin_download_failure_does_not_record_a_learning_project(tmp_path, monkeypatch):
    from types import SimpleNamespace

    root = tmp_path / "learning"
    monkeypatch.setattr(downloads, "project_directory", lambda url: root)
    downloader = SimpleNamespace(download_video=lambda *args, **kwargs: {"success": False, "error": "failed"})
    result = downloads.download_douyin(downloader, "https://v.douyin.com/share/", video_info={"aweme_id": "123456"})
    assert not result["success"]
    assert not (root / MANIFEST).exists()


@pytest.mark.parametrize("filename,class_name", [
    ("main.py", "WorkerThread"),
    ("main.py", "DouyinDownloadThread"),
    ("src/gui/workers/worker_thread.py", "WorkerThread"),
    ("src/gui/workers/douyin_threads.py", "DouyinDownloadThread"),
])
@pytest.mark.parametrize("processing", [False, True])
def test_desktop_douyin_entry_points_route_processed_media_to_learning(monkeypatch, tmp_path, filename, class_name, processing):
    # Execute the actual worker methods with signal stubs, avoiding startup of
    # the application's GUI, servers, and device services during this test.
    import ast
    import os
    import sys
    from types import SimpleNamespace
    from src import youtube_transcriber as yt
    import douyin

    class Signal:
        def __init__(self, *args):
            self.events = []

        def emit(self, *args):
            self.events.append(args)

    info = {"aweme_id": "7660369906369629476"}
    calls = []
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    result = {"success": True, "files": {"video": [str(video)]},
              "downloaded_files": [{"type": "video", "path": str(video)}]}

    def download(*args, **kwargs):
        calls.append("download")
        return result

    def learning(*args, **kwargs):
        assert kwargs["video_info"] == info
        calls.append("learning")
        return result

    downloader = SimpleNamespace(download_video=download, get_video_info=lambda url: info)
    utils = SimpleNamespace(validate_url=lambda url: True, is_user_profile_url=lambda url: False,
                            get_video_info_summary=lambda info: "test")
    monkeypatch.setattr(douyin, "DouyinDownloader", lambda *args, **kwargs: downloader)
    monkeypatch.setattr(douyin, "DouyinUtils", utils)
    monkeypatch.setattr(downloads, "download_douyin", learning)
    monkeypatch.setattr(yt, "process_local_video", lambda *args, **kwargs: str(video))
    monkeypatch.setitem(sys.modules, "youtube_transcriber", yt)
    monkeypatch.setitem(sys.modules, "learning.downloads", downloads)
    namespace = {"QThread": object, "pyqtSignal": Signal, "os": os,
                 "DEFAULT_SUMMARY_DIR": str(tmp_path), "DOUYIN_AVAILABLE": True,
                 "DouyinDownloader": douyin.DouyinDownloader, "DouyinUtils": utils}
    source_path = Path(__file__).resolve().parents[1] / filename
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source_path), "exec"), namespace)
    if class_name == "WorkerThread":
        worker = namespace[class_name]("youtube", {
            "youtube_url": "https://www.douyin.com/video/7660369906369629476",
            "enable_transcription": processing, "generate_article": False,
        })
        worker.process_youtube()
        assert worker.finished_signal.events[-1][1] is True
    else:
        worker = namespace[class_name]("https://www.douyin.com/video/7660369906369629476",
                                       {"enable_transcription": processing, "generate_article": False}, info)
        worker.run()
        assert worker.finished_signal.events[-1][0] is True
    assert calls == ["learning" if processing else "download"]

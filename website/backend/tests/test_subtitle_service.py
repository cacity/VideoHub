import pytest
from pathlib import Path
from subtitle_service import (
    SubtitleService,
    ValidationError,
    NotFoundError,
    choose_available_language,
    convert_subtitle_content,
    extract_preview,
    safe_join,
    validate_format,
    validate_language,
    validate_youtube_url,
)


def test_validate_youtube_url_accepts_single_video():
    assert validate_youtube_url("https://www.youtube.com/watch?v=abc123&list=PL1") == "https://www.youtube.com/watch?v=abc123"
    assert validate_youtube_url("https://youtu.be/abc123?si=share") == "https://youtu.be/abc123"


def test_validate_youtube_url_rejects_deceptive_hosts_and_playlists():
    with pytest.raises(ValidationError):
        validate_youtube_url("https://youtube.com.example.com/watch?v=abc123")
    with pytest.raises(ValidationError):
        validate_youtube_url("https://www.youtube.com/playlist?list=PL123")
    with pytest.raises(ValidationError):
        validate_youtube_url("ftp://www.youtube.com/watch?v=abc123")


def test_validate_format_and_language():
    assert validate_format("srt") == "SRT"
    assert validate_format("SRT") == "SRT"
    with pytest.raises(ValidationError):
        validate_format("mp4")
    assert validate_language("zh-Hans") == "zh-Hans"
    with pytest.raises(ValidationError):
        validate_language("../secret")


def test_choose_available_language_aliases():
    assert choose_available_language("zh-Hans", {"zh-CN": {}}, {}) == "zh-CN"
    assert choose_available_language("zh", {"zh-CN": {}}, {}) == "zh-CN"
    assert choose_available_language("en", {}, {"en-orig": {}}) == "en-orig"
    with pytest.raises(ValidationError):
        choose_available_language("ja", {}, {})


def test_convert_srt_to_txt_and_preview():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHello <b>world</b>\n\n2\n00:00:03,000 --> 00:00:04,000\nSecond line\n"
    txt = convert_subtitle_content(srt, ".srt", "TXT")
    assert txt == "Hello world\nSecond line\n"
    preview = extract_preview(srt, "SRT")
    assert preview[0]["time"] == "00:00:01,000"
    assert preview[0]["text"] == "Hello world"


def test_convert_vtt_to_srt():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello\n"
    srt = convert_subtitle_content(vtt, ".vtt", "SRT")
    assert srt == "1\n00:00:01,000 --> 00:00:02,000\nHello"


def test_safe_join_blocks_path_escape(tmp_path):
    assert safe_join(tmp_path, "abc", "file.srt").resolve() == tmp_path / "abc" / "file.srt"
    with pytest.raises(ValidationError):
        safe_join(tmp_path, "..", "secret")


def test_resolve_file_uses_metadata_and_containment(tmp_path):
    service = SubtitleService(tmp_path)
    file_dir = tmp_path / "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    file_dir.mkdir()
    (file_dir / "subtitle.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    (file_dir / "metadata.json").write_text('{"filename":"subtitle.srt"}', encoding="utf-8")

    assert service.resolve_file("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").resolve() == (file_dir / "subtitle.srt").resolve()
    with pytest.raises(NotFoundError):
        service.resolve_file("../bad")

from pathlib import Path

from src.chinese_tts import ChineseTTS
from src import youtube_transcriber
from src.dubbing_engine import VideoDubbingEngine


ASS_HEADER = """[Script Info]
Title: Bilingual Subtitles
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,18,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1
Style: Secondary,Arial,18,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def test_ass_parser_prefers_chinese_line_from_bilingual_timeline(tmp_path):
    subtitle = tmp_path / "bilingual.ass"
    subtitle.write_text(
        ASS_HEADER
        + "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hello, everyone.\n"
        + "Dialogue: 0,0:00:00.00,0:00:02.00,Secondary,,0,0,0,,大家好。\n",
        encoding="utf-8",
    )

    parser = ChineseTTS.__new__(ChineseTTS)
    segments = parser._parse_srt(str(subtitle))

    assert len(segments) == 1
    assert segments[0]["text"] == "大家好。"
    assert segments[0]["start"] == 0.0
    assert segments[0]["end"] == 2.0


def test_ass_translation_reuses_existing_target_and_preserves_structure(monkeypatch, tmp_path):
    subtitle = tmp_path / "bilingual.ass"
    subtitle.write_text(
        ASS_HEADER
        + "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hello, everyone.\n"
        + "Dialogue: 0,0:00:00.00,0:00:02.00,Secondary,,0,0,0,,大家好。\n",
        encoding="utf-8",
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Existing target-language ASS line should not be translated again")

    monkeypatch.setattr(youtube_transcriber, "translate_text", fail_if_called)
    result = youtube_transcriber.translate_subtitle_file(
        str(subtitle),
        target_language="zh-CN",
        output_dir=str(tmp_path),
        enable_translation_polish=True,
    )

    content = Path(result).read_text(encoding="utf-8")
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    assert "[Script Info]" in content
    assert "Title: Bilingual Subtitles" in content
    assert "[Events]" in content
    assert len(dialogue_lines) == 1
    assert dialogue_lines[0].endswith(",大家好。")
    assert "[脚本信息]" not in content
    assert "对话:" not in content


def test_ass_translation_only_sends_dialogue_text_to_translator(monkeypatch, tmp_path):
    subtitle = tmp_path / "source.ass"
    subtitle.write_text(
        ASS_HEADER
        + "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Hello, everyone.\n",
        encoding="utf-8",
    )
    received = []

    def fake_translate(text, target_language):
        received.append((text, target_language))
        return "大家好。"

    monkeypatch.setattr(youtube_transcriber, "translate_text", fake_translate)
    result = youtube_transcriber.translate_subtitle_file(
        str(subtitle),
        target_language="zh-CN",
        output_dir=str(tmp_path),
        enable_translation_polish=False,
    )

    content = Path(result).read_text(encoding="utf-8")
    assert received == [("Hello, everyone.", "zh-CN")]
    assert "Title: Bilingual Subtitles" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,大家好。" in content


def test_dubbing_rejects_subtitle_timeline_longer_than_video(monkeypatch, tmp_path):
    from src import dubbing_engine

    subtitle = tmp_path / "stale.ass"
    subtitle.write_text(
        ASS_HEADER
        + "Dialogue: 0,0:00:00.00,0:02:00.00,Secondary,,0,0,0,,这不是当前视频的字幕。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dubbing_engine, "get_video_duration", lambda _path: 10.0)

    engine = VideoDubbingEngine.__new__(VideoDubbingEngine)
    try:
        engine._validate_subtitle_timeline("video.mp4", str(subtitle))
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("A stale subtitle timeline should be rejected")

    assert "字幕与视频时长明显不匹配" in message
    assert "清空配音页的‘已有字幕’输入框" in message

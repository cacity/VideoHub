from pathlib import Path

import pytest

from src.learning.project import classify
from src.learning.subtitles import parse, read_track
from src.subtitle_tracks import save_language_tracks, snapshot_track


def test_separate_tracks_preserve_text_time_and_previous_exports(tmp_path):
    rows = [{"start": 1.25, "end": 3.5, "source": "Hello,\nworld.", "translation": "你好，世界。"}]
    outputs = save_language_tracks(rows, tmp_path / "lesson_polished.srt", "en", "zh-CN")
    assert set(outputs) == {"source", "target"}
    assert "你好" not in Path(outputs["source"]).read_text(encoding="utf-8")
    assert "Hello" not in Path(outputs["target"]).read_text(encoding="utf-8")
    assert read_track(Path(outputs["target"]))["cues"][0]["start"] == 1.25
    assert save_language_tracks(rows, tmp_path / "lesson_polished.srt", "en", "zh-CN") == outputs
    updated = save_language_tracks(
        [{**rows[0], "translation": "新的译文。"}], tmp_path / "lesson_polished.srt", "en", "zh-CN"
    )
    assert updated["source"] == outputs["source"] and updated["target"] != outputs["target"]
    assert "你好" in Path(outputs["target"]).read_text(encoding="utf-8")
    assert classify(Path(outputs["source"])) == ("source", "en")
    assert classify(Path(outputs["target"])) == ("target", "zh-CN")
    # Explicit role wins even when the original name includes polished or Chinese.
    assert classify(tmp_path / "中文课程_polished.source.en.abc.srt") == ("source", "en")


def test_snapshot_never_replaces_an_edited_export_and_rejects_bad_times(tmp_path):
    cues = [{"start": 0, "end": 2, "text": "Keep this."}]
    path = snapshot_track(cues, tmp_path, "lesson", "source", "en")
    path.write_text("user edit", encoding="utf-8")
    with pytest.raises(ValueError, match="已被修改"):
        snapshot_track(cues, tmp_path, "lesson", "source", "en")
    assert path.read_text() == "user edit"
    with pytest.raises(ValueError, match="时间"):
        snapshot_track([{**cues[0], "end": float("inf")}], tmp_path, "lesson", "source", "en")


def test_language_files_stay_associated_with_long_video_names_in_multi_video_projects(tmp_path):
    from src.series_project import normalize_asset_stem, subtitle_role
    from src.learning.imports import subtitle_candidates

    title = "A_long_video_title_for_learning_" * 3
    rows = [{"start": 0, "end": 2, "source": "Hello.", "translation": "你好。"}]
    files = save_language_tracks(rows, tmp_path / (title + "_polished.srt"), "en", "zh-CN")
    assert all(normalize_asset_stem(Path(path).stem) == normalize_asset_stem(title) for path in files.values())
    assert subtitle_role(files["source"]) == "source" and subtitle_role(files["target"]) == "polished"
    video = tmp_path / (title + ".mp4")
    video.write_bytes(b"media")
    found = subtitle_candidates(str(video), root=tmp_path)
    assert {(r["role"], r["language"]) for r in found} == {("source", "en"), ("target", "zh-CN")}


def test_incomplete_bilingual_cue_never_leaks_english_into_chinese():
    text = "1\n00:00:00,000 --> 00:00:02,000\nHello.\n你好。\n\n2\n00:00:03,000 --> 00:00:05,000\nNot translated yet.\n"
    assert [c["text"] for c in parse(text, role="source")] == ["Hello.", "Not translated yet."]
    assert [c["text"] for c in parse(text, role="target")] == ["你好。"]


@pytest.mark.parametrize("entry", ["unified", "bilingual"])
def test_transcription_entrypoints_also_save_plain_language_files(tmp_path, monkeypatch, entry):
    from src import youtube_transcriber as yt

    audio = tmp_path / "lesson.mp3"
    audio.write_bytes(b"audio")
    result = {"language": "en", "text": "Hello.", "segments": [{"start": 0, "end": 2, "text": "Hello."}]}
    monkeypatch.setattr(yt, "configure_cuda_for_whisper", lambda: "cpu")
    monkeypatch.setattr(yt, "get_optimal_whisper_params", lambda device: {})
    monkeypatch.setattr(yt, "run_whisper_transcription", lambda *a, **k: (result, 0.1, 0.1))
    monkeypatch.setattr(yt, "translate_text", lambda *a, **k: "你好。")
    monkeypatch.setattr(yt, "should_polish_translation", lambda *a: True)
    monkeypatch.setattr(
        yt,
        "polish_subtitle_translations_with_deepseek",
        lambda rows: [{**r, "translation": "润色译文。"} for r in rows],
    )
    if entry == "unified":
        _, mixed = yt.transcribe_audio_unified(
            str(audio), output_dir=str(tmp_path), subtitle_dir=str(tmp_path), generate_subtitles=True
        )
    else:
        mixed = yt.create_bilingual_subtitles(str(audio), output_dir=str(tmp_path))
    assert mixed and Path(mixed).is_file()
    originals = list(tmp_path.glob("*.source.en.*.srt"))
    translations = list(tmp_path.glob("*.target.zh-CN.*.srt"))
    assert len(originals) == len(translations) == 1
    assert read_track(originals[0])["cues"][0]["text"] == "Hello."
    assert read_track(translations[0])["cues"][0]["text"] == "润色译文。"
    assert "Hello." in Path(mixed).read_text(encoding="utf-8")

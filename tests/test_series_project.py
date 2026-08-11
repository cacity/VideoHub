import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from series_project import (  # noqa: E402
    discover_series_project,
    list_series_videos,
    normalize_asset_stem,
    refresh_series_project_manifest,
)


def test_series_project_matches_video_and_subtitle_name_variants(tmp_path):
    (tmp_path / "My Show E01.mp4").touch()
    subtitles = tmp_path / "subtitles"
    subtitles.mkdir()
    (subtitles / "My_Show_E01.srt").write_text("source", encoding="utf-8")
    (subtitles / "My_Show_E01_google.srt").write_text("translated", encoding="utf-8")
    (subtitles / "My_Show_E01_zh_CN_polished.srt").write_text("polished", encoding="utf-8")

    project = discover_series_project(tmp_path)

    assert len(project["episodes"]) == 1
    episode = project["episodes"][0]
    assert episode["video"] == "My Show E01.mp4"
    assert episode["subtitles"] == {
        "source": ["subtitles/My_Show_E01.srt"],
        "translated": ["subtitles/My_Show_E01_google.srt"],
        "polished": ["subtitles/My_Show_E01_zh_CN_polished.srt"],
    }


def test_refresh_manifest_creates_portable_project_layout(tmp_path):
    (tmp_path / "Episode 2.mkv").touch()
    (tmp_path / "Episode 10.mkv").touch()

    manifest_path = refresh_series_project_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert [item["id"] for item in manifest["episodes"]] == ["Episode 2", "Episode 10"]
    assert manifest["directories"] == {
        "videos": ".",
        "audio": "audio",
        "subtitles": "subtitles",
        "transcripts": "transcripts",
        "summaries": "summaries",
        "videos_with_subtitles": "videos_with_subtitles",
    }
    assert str(tmp_path) not in manifest_path.read_text(encoding="utf-8")
    assert all((tmp_path / name).is_dir() for name in manifest["directories"].values() if name != ".")


def test_list_series_videos_ignores_generated_subdirectories(tmp_path):
    (tmp_path / "Episode 1.mp4").touch()
    generated = tmp_path / "videos_with_subtitles"
    generated.mkdir()
    (generated / "Episode 1.mp4").touch()

    assert list_series_videos(tmp_path) == [tmp_path / "Episode 1.mp4"]


def test_normalize_asset_stem_keeps_episode_number():
    assert normalize_asset_stem("Show E03_zh-CN_google") == "showe03"

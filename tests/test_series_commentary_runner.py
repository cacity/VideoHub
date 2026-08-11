import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = (
    ROOT
    / ".agents"
    / "skills"
    / "videohub-film-commentary"
    / "scripts"
)
STORY_SCRIPT_DIR = ROOT / ".agents" / "skills" / "videohub-story-editor" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(STORY_SCRIPT_DIR))

from series_commentary_common import (  # noqa: E402
    SeriesConfigError,
    load_series_project,
    parse_episode_selector,
    source_starts,
)


def load_runner():
    path = SCRIPT_DIR / "run_series_commentary.py"
    spec = importlib.util.spec_from_file_location("run_series_commentary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def write_project(tmp_path: Path, *, starts=None) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "episode_specs.json").write_text(
        json.dumps(
            {
                "1": {
                    "duration": 60,
                    "summary": "第一集摘要",
                    "texts": ["第一段", "第二段"],
                    **({"source_starts": starts} if starts is not None else {}),
                },
                "2": {
                    "duration": 30,
                    "summary": "第二集摘要",
                    "texts": ["一段旁白"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (data / "series_spec.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "series": {"title": "测试剧", "slug": "test_series"},
                "paths": {"episode_specs": "data/episode_specs.json"},
                "production": {
                    "resolution": [1080, 1920],
                    "narration": {
                        "provider": "minimax",
                        "model": "speech-2.8-turbo",
                        "voice_id": "test-voice",
                        "speed": 1.2,
                    },
                    "audio": {
                        "original_audio_volume": 0.0,
                        "source_audio_volume": 0.0,
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_load_series_project_and_episode_selector(tmp_path):
    project = load_series_project(write_project(tmp_path))

    assert project.config["production"]["resolution"] == [1080, 1920]
    assert parse_episode_selector("1-2", set(project.episodes)) == [1, 2]
    assert parse_episode_selector("2,1", set(project.episodes)) == [1, 2]


def test_invalid_source_start_count_is_rejected(tmp_path):
    root = write_project(tmp_path, starts=[0.0])

    with pytest.raises(SeriesConfigError, match="must match narration block count"):
        load_series_project(root)


def test_automatic_source_starts_cover_available_span():
    spec = {"duration": 60, "texts": ["一", "二", "三"]}

    assert source_starts(spec, 120) == [0.0, 50.0, 100.0]


def test_preflight_report_uses_project_configuration(tmp_path, monkeypatch):
    runner = load_runner()
    project = load_series_project(write_project(tmp_path))
    source_dir = tmp_path / "data" / "source_episodes"
    subtitle_dir = tmp_path / "data" / "subtitles"
    source_dir.mkdir()
    subtitle_dir.mkdir()
    (source_dir / "episode_01.mp4").write_bytes(b"video")
    (subtitle_dir / "episode_01.srt").write_text("subtitle", encoding="utf-8")
    monkeypatch.setattr(
        runner,
        "probe",
        lambda _path, _ffprobe: {
            "format": {"duration": "120.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
    )

    report = runner.preflight_episode(project, 1, "ffprobe")

    assert report["status"] == "PASS"
    assert report["target_duration_sec"] == 60
    assert report["source_starts_sec"] == [0.0, 90.0]


def test_manifest_video_path_supports_both_manifest_shapes(tmp_path):
    audit_path = SCRIPT_DIR / "audit_series_episode.py"
    spec = importlib.util.spec_from_file_location("audit_series_episode", audit_path)
    audit = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(audit)

    assert audit.manifest_video_path(tmp_path, {"video_file": "final.mp4"}) == tmp_path / "final.mp4"
    assert audit.manifest_video_path(
        tmp_path, {"assets": [{"name": "delivery.mp4"}]}
    ) == tmp_path / "delivery.mp4"


def test_generated_series_plans_pass_existing_validators(tmp_path):
    runner = load_runner()
    project = load_series_project(write_project(tmp_path))
    paths = runner.episode_paths(project, 1)
    evidence = {
        "schema_version": "1.0",
        "job_id": "test_series_ep01",
        "source": {
            "video_path": str(paths["video"]),
            "fingerprint": "fixture-fingerprint",
            "duration_sec": 120.0,
        },
        "subtitles": [
            {"id": "sub-001", "start_sec": 0.0, "end_sec": 20.0, "source_text": "开端"},
            {"id": "sub-002", "start_sec": 20.0, "end_sec": 60.0, "source_text": "发展"},
            {"id": "sub-003", "start_sec": 90.0, "end_sec": 120.0, "source_text": "结果"},
        ],
        "scenes": [{"id": "scene-001", "start_sec": 0.0, "end_sec": 120.0}],
        "keyframes": [{"id": "frame-001"}],
        "visual_candidates": [],
        "analysis_chunks": [{"id": "chunk-001", "summary": "完整剧情证据分块"}],
    }
    analysis = runner.make_analysis(project, 1, evidence)
    plan, _starts = runner.make_story_plan(
        project, 1, paths, evidence, source_duration=120.0
    )
    narration = runner.make_narration_plan(project, 1, paths["plan"])

    from validate_narration_plan import validate_narration_plan
    from validate_story_analysis import validate_analysis
    from validate_story_plan import validate_plan

    analysis_errors, _ = validate_analysis(analysis, evidence)
    plan_errors, _ = validate_plan(plan, evidence=evidence, analysis=analysis)
    narration_errors, _ = validate_narration_plan(
        narration, plan, evidence, analysis
    )

    assert analysis_errors == []
    assert plan_errors == []
    assert narration_errors == []

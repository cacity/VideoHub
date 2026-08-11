import json
from pathlib import Path

import pytest

from src.story_timeline_server import StoryTimelineService, create_app


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def story_workspace(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project001_demo_story"
    job_dir = project / "docs" / "story_job"
    source_video = project / "data" / "source.mp4"
    source_video.parent.mkdir(parents=True)
    source_video.write_bytes(b"not-a-real-video")
    evidence_path = job_dir / "evidence_pack.json"
    analysis_path = job_dir / "story_analysis.json"
    plan_path = job_dir / "story_plan.json"
    narration_path = job_dir / "narration_plan.json"

    write_json(
        evidence_path,
        {
            "schema_version": "1.0",
            "job_id": "demo-job",
            "source": {
                "video_path": str(source_video),
                "duration_sec": 20.0,
                "language": "en",
                "video": {"width": 1920, "height": 1080, "fps": 25.0},
            },
            "subtitles": [
                {
                    "id": "sub-001",
                    "start_sec": 1.0,
                    "end_sec": 3.0,
                    "source_text": "first",
                    "target_text": "第一句",
                    "speaker": "A",
                },
                {
                    "id": "sub-002",
                    "start_sec": 11.0,
                    "end_sec": 13.0,
                    "source_text": "second",
                    "target_text": "第二句",
                    "speaker": "B",
                },
            ],
            "scenes": [
                {"id": "scene-001", "start_sec": 0.0, "end_sec": 10.0},
                {"id": "scene-002", "start_sec": 10.0, "end_sec": 20.0},
            ],
            "visual_candidates": [],
            "keyframes": [],
            "analysis_chunks": [],
        },
    )
    write_json(
        analysis_path,
        {
            "schema_version": "1.0",
            "job_id": "demo-job",
            "events": [{"id": "event-001"}],
            "themes": [],
            "visual_findings": [],
            "continuity_constraints": [],
            "story_options": [],
        },
    )
    write_json(
        plan_path,
        {
            "schema_version": "1.0",
            "job_id": "demo-job",
            "evidence_pack_path": str(evidence_path),
            "story_analysis_path": str(analysis_path),
            "source": {"video_path": str(source_video), "language": "en"},
            "settings": {"target_duration_sec": 20.0},
            "classification": {"content_type": "film"},
            "story": {"title": "Demo"},
            "segments": [
                {
                    "id": "seg-001",
                    "output_order": 1,
                    "kind": "dialogue",
                    "story_role": "hook",
                    "source_start_sec": 0.0,
                    "source_end_sec": 10.0,
                    "output_start_sec": 0.0,
                    "output_end_sec": 10.0,
                    "playback_rate": 1.0,
                    "source_subtitle_ids": ["sub-001"],
                    "source_scene_ids": ["scene-001"],
                    "analysis_refs": ["event-001"],
                    "source_text": "first",
                    "target_text": "第一句",
                    "speaker": "A",
                    "audio_mode": "source",
                    "story_reason": "first clip",
                    "transition": "cut",
                },
                {
                    "id": "seg-002",
                    "output_order": 2,
                    "kind": "dialogue",
                    "story_role": "resolution",
                    "source_start_sec": 10.0,
                    "source_end_sec": 20.0,
                    "output_start_sec": 10.0,
                    "output_end_sec": 20.0,
                    "playback_rate": 1.0,
                    "source_subtitle_ids": ["sub-002"],
                    "source_scene_ids": ["scene-002"],
                    "analysis_refs": ["event-001"],
                    "source_text": "second",
                    "target_text": "第二句",
                    "speaker": "B",
                    "audio_mode": "source",
                    "story_reason": "second clip",
                    "transition": "cut",
                },
            ],
            "output": {"video_path": str(project / "outputs" / "demo.mp4")},
        },
    )
    write_json(
        narration_path,
        {
            "schema_version": "1.0",
            "job_id": "demo-job",
            "style": "film_commentary",
            "settings": {
                "original_audio_volume": 0.3,
                "source_audio_volume": 1.0,
            },
            "tts": {"provider": "minimax", "voice_id": "demo", "speed": 1.0},
            "blocks": [
                {
                    "id": "nar-001",
                    "start_sec": 1.0,
                    "end_sec": 5.0,
                    "text": "第一段旁白",
                    "purpose": "hook",
                    "evidence_refs": ["seg-001"],
                },
                {
                    "id": "nar-002",
                    "start_sec": 12.0,
                    "end_sec": 16.0,
                    "text": "第二段旁白",
                    "purpose": "resolution",
                    "evidence_refs": ["seg-002"],
                },
            ],
            "source_audio_windows": [
                {
                    "id": "anchor-001",
                    "start_sec": 6.0,
                    "end_sec": 9.0,
                    "purpose": "source line",
                    "evidence_refs": ["seg-001"],
                }
            ],
        },
    )
    return tmp_path, plan_path


def test_discovers_and_imports_five_tracks(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)

    projects = service.list_projects()
    assert len(projects) == 1
    timeline = service.load_timeline(projects[0]["id"])

    assert len(timeline["clips"]) == 2
    assert len(timeline["tracks"]["original_audio"]) == 2
    assert len(timeline["tracks"]["narration"]) == 2
    assert len(timeline["tracks"]["source_audio"]) == 1
    assert timeline["tracks"]["narration"][1]["segment_id"] == "seg-002"
    assert timeline["tracks"]["narration"][1]["local_start_sec"] == 2.0


def test_saves_reordered_split_revision_without_touching_original(story_workspace):
    workspace, original_plan_path = story_workspace
    original_text = original_plan_path.read_text(encoding="utf-8")
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    timeline = service.load_timeline(project_id)
    assert timeline["settings"]["subtitle_position_percent"] == 90.0
    timeline["settings"]["subtitle_position_percent"] = 68.0

    first, second = timeline["clips"]
    first_left = {**first, "id": "seg-001-a", "source_end_sec": 5.0}
    first_right = {**first, "id": "seg-001-b", "source_start_sec": 5.0}
    timeline["clips"] = [second, first_left, first_right]
    timeline["tracks"]["narration"] = [
        {**timeline["tracks"]["narration"][1]},
        {
            **timeline["tracks"]["narration"][0],
            "segment_id": "seg-001-a",
        },
    ]
    timeline["tracks"]["source_audio"] = [
        {
            **timeline["tracks"]["source_audio"][0],
            "segment_id": "seg-001-b",
            "local_start_sec": 1.0,
            "local_end_sec": 4.0,
        }
    ]
    timeline["tracks"]["subtitles"] = [
        item
        for item in timeline["tracks"]["subtitles"]
        if item["segment_id"] == "seg-002"
    ]

    saved = service.save_revision(project_id, timeline, "unit test")
    revision_dir = workspace / "project001_demo_story" / "revisions" / saved["revisionId"]
    compiled = json.loads((revision_dir / "story_plan.json").read_text(encoding="utf-8"))
    narration = json.loads((revision_dir / "narration_plan.json").read_text(encoding="utf-8"))

    assert [item["id"] for item in compiled["segments"]] == [
        "seg-002",
        "seg-001-a",
        "seg-001-b",
    ]
    assert [item["output_start_sec"] for item in compiled["segments"]] == [0.0, 10.0, 15.0]
    assert narration["blocks"][0]["start_sec"] == 2.0
    assert narration["blocks"][1]["start_sec"] == 11.0
    assert narration["settings"]["audio_strategy"] == "hybrid_source_anchors"
    assert compiled["settings"]["subtitle_position_percent"] == 68.0
    subtitle_text = (revision_dir / "timeline_subtitles.srt").read_text(
        encoding="utf-8"
    )
    assert "第二段旁白" in subtitle_text
    for key in (
        "video_path",
        "source_subtitle_path",
        "translated_subtitle_path",
        "bilingual_subtitle_path",
        "qa_report_path",
    ):
        assert revision_dir.resolve() in Path(compiled["output"][key]).resolve().parents
    assert original_plan_path.read_text(encoding="utf-8") == original_text


def test_rejects_subtitle_position_outside_safe_frame(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    timeline = service.load_timeline(project_id)
    timeline["settings"]["subtitle_position_percent"] = 98

    with pytest.raises(ValueError, match="Subtitle position"):
        service.save_revision(project_id, timeline)


def test_crossfade_layout_and_audio_controls_are_compiled(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    timeline = service.load_timeline(project_id)
    timeline["clips"][0]["fade_in_sec"] = 0.3
    timeline["clips"][0]["fade_out_sec"] = 0.4
    timeline["clips"][0]["volume_keyframes"] = [
        {"id": "volume-1", "time_sec": 0.0, "volume": 0.3},
        {"id": "volume-2", "time_sec": 5.0, "volume": 1.0},
    ]
    timeline["clips"][1]["transition"] = "crossfade"
    timeline["clips"][1]["transition_duration_sec"] = 1.0

    saved = service.save_revision(project_id, timeline)
    plan_path = (
        workspace
        / "project001_demo_story"
        / "revisions"
        / saved["revisionId"]
        / "story_plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    assert plan["segments"][1]["output_start_sec"] == 9.0
    assert plan["segments"][1]["output_end_sec"] == 19.0
    assert plan["settings"]["target_duration_sec"] == 19.0
    assert plan["segments"][0]["fade_in_sec"] == 0.3
    assert plan["segments"][0]["volume_keyframes"][1]["volume"] == 1.0


def test_registers_an_additional_local_video_source(story_workspace, monkeypatch):
    workspace, _ = story_workspace
    extra = workspace / "extra.mp4"
    extra.write_bytes(b"video")
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    monkeypatch.setattr(
        service,
        "_probe_video",
        lambda _path: {
            "duration_sec": 12.0,
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "audio_present": True,
        },
    )

    source = service.register_source(project_id, str(extra))
    timeline = service.load_timeline(project_id)

    assert source["id"].startswith("source-")
    assert source["filename"] == "extra.mp4"
    assert any(item["id"] == source["id"] for item in timeline["sources"])


def test_rejects_track_item_outside_trimmed_clip(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    timeline = service.load_timeline(project_id)
    timeline["clips"][0]["source_end_sec"] = 2.0

    with pytest.raises(ValueError, match="outside clip"):
        service.save_revision(project_id, timeline)


def test_switches_to_narration_only_when_source_windows_are_removed(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    timeline = service.load_timeline(project_id)
    timeline["tracks"]["source_audio"] = []

    saved = service.save_revision(project_id, timeline)
    narration_path = (
        workspace
        / "project001_demo_story"
        / "revisions"
        / saved["revisionId"]
        / "narration_plan.json"
    )
    narration = json.loads(narration_path.read_text(encoding="utf-8"))

    assert narration["settings"]["audio_strategy"] == "narration_only"


def test_custom_narration_asset_is_served_from_project_cache(story_workspace):
    workspace, _ = story_workspace
    service = StoryTimelineService(workspace)
    project_id = service.list_projects()[0]["id"]
    cache_dir = (
        workspace
        / "project001_demo_story"
        / ".story_editor_cache"
        / "narration"
        / "minimax"
    )
    cache_dir.mkdir(parents=True)
    custom = cache_dir / "custom-test.wav"
    custom.write_bytes(b"RIFF" + b"0" * 100)

    assert service.narration_asset(project_id, "custom-test") == custom.resolve()


def test_api_rejects_revision_path_traversal(story_workspace):
    workspace, _ = story_workspace
    app = create_app(workspace)
    project_id = app.config["STORY_TIMELINE_SERVICE"].list_projects()[0]["id"]
    client = app.test_client()

    response = client.get(
        f"/api/story-editor/projects/{project_id}?revision=..%2Foutside"
    )

    assert response.status_code == 400

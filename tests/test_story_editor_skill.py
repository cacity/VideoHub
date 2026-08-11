import sys
from pathlib import Path

import pytest

SKILL_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "videohub-story-editor"
    / "scripts"
)
sys.path.insert(0, str(SKILL_SCRIPTS))

from build_douyin_publish_package import (  # noqa: E402
    normalize_hashtags,
    validate_caption,
)
from render_story import (  # noqa: E402
    apply_external_translation,
    build_source_volume_expression,
    build_volume_keyframe_expression,
    combine_commentary_subtitles,
    final_subtitle_timeline,
    rebuild_subtitle_timeline,
    restore_or_render_segment,
    select_subtitle_cues_for_windows,
)
from story_pipeline_common import (  # noqa: E402
    SubtitleCue,
    pair_translations,
    parse_srt_or_vtt,
    write_ass,
)
from validate_narration_plan import validate_narration_plan  # noqa: E402


def test_parse_srt_extracts_speaker_labels():
    cues = parse_srt_or_vtt(
        """1
00:00:00,500 --> 00:00:02,500
主持人：为什么失败？

2
00:00:03,000 --> 00:00:04,500
Guest: We solved the wrong problem.
"""
    )

    assert len(cues) == 2
    assert cues[0].speaker == "主持人"
    assert cues[0].text == "为什么失败？"
    assert cues[1].speaker == "Guest"
    assert cues[1].text == "We solved the wrong problem."


def test_ass_subtitle_position_uses_authored_vertical_percentage(tmp_path):
    output = tmp_path / "positioned.ass"
    write_ass(
        output,
        [
            {
                "start_sec": 0.0,
                "end_sec": 2.0,
                "source_text": "",
                "target_text": "向上移动的解说字幕",
            }
        ],
        "translated",
        position_percent=70,
    )

    content = output.read_text(encoding="utf-8")
    assert "Target,,0,0,324,,向上移动的解说字幕" in content


def test_pair_translations_uses_timeline_overlap():
    source = [
        SubtitleCue(0.0, 1.0, "第一句"),
        SubtitleCue(2.0, 3.0, "第二句"),
    ]
    target = [
        SubtitleCue(2.02, 3.02, "Second"),
        SubtitleCue(0.02, 1.02, "First"),
    ]

    assert pair_translations(source, target) == ["First", "Second"]


def test_rebuild_subtitles_follows_reordered_output_timeline():
    evidence = {
        "subtitles": [
            {
                "id": "sub-001",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "speaker": "A",
                "source_text": "First in source",
                "target_text": "源片第一句",
            },
            {
                "id": "sub-002",
                "start_sec": 4.0,
                "end_sec": 5.0,
                "speaker": "B",
                "source_text": "Second in source",
                "target_text": "源片第二句",
            },
        ]
    }
    plan = {
        "segments": [
            {
                "id": "seg-001",
                "kind": "dialogue",
                "source_start_sec": 4.0,
                "source_end_sec": 5.0,
                "output_start_sec": 0.0,
                "output_end_sec": 1.0,
                "playback_rate": 1.0,
                "source_subtitle_ids": ["sub-002"],
            },
            {
                "id": "seg-002",
                "kind": "dialogue",
                "source_start_sec": 1.0,
                "source_end_sec": 2.0,
                "output_start_sec": 1.0,
                "output_end_sec": 2.0,
                "playback_rate": 1.0,
                "source_subtitle_ids": ["sub-001"],
            },
        ]
    }

    rebuilt = rebuild_subtitle_timeline(plan, evidence)

    assert [item["source_subtitle_id"] for item in rebuilt] == ["sub-002", "sub-001"]
    assert rebuilt[0]["start_sec"] == 0.0
    assert rebuilt[1]["start_sec"] == 1.0


def test_rebuild_subtitles_can_include_all_intersecting_cues():
    evidence = {
        "subtitles": [
            {
                "id": "sub-001",
                "start_sec": 1.0,
                "end_sec": 2.0,
                "speaker": "A",
                "source_text": "Explicit cue",
                "target_text": "显式字幕",
            },
            {
                "id": "sub-002",
                "start_sec": 2.2,
                "end_sec": 3.0,
                "speaker": "B",
                "source_text": "Unlisted cue",
                "target_text": "未列出的字幕",
            },
        ]
    }
    plan = {
        "segments": [
            {
                "id": "seg-001",
                "kind": "visual",
                "source_start_sec": 1.5,
                "source_end_sec": 3.0,
                "output_start_sec": 0.0,
                "output_end_sec": 1.5,
                "playback_rate": 1.0,
                "source_subtitle_ids": ["sub-001"],
            }
        ]
    }

    rebuilt = rebuild_subtitle_timeline(
        plan,
        evidence,
        subtitle_policy="all-intersecting",
    )

    assert [item["source_subtitle_id"] for item in rebuilt] == [
        "sub-001",
        "sub-002",
    ]
    assert rebuilt[0]["start_sec"] == 0.0
    assert rebuilt[0]["end_sec"] == 0.5
    assert rebuilt[1]["start_sec"] == 0.7
    assert rebuilt[1]["end_sec"] == 1.5


def test_post_edit_translation_is_attached_to_final_timeline(tmp_path):
    translated = tmp_path / "story_zh-CN.srt"
    translated.write_text(
        """1
00:00:00,000 --> 00:00:01,000
剪辑后的第一句

2
00:00:01,000 --> 00:00:02,000
剪辑后的第二句
""",
        encoding="utf-8",
    )
    cues = [
        {
            "start_sec": 0.0,
            "end_sec": 1.0,
            "source_text": "Second in source",
            "target_text": "",
        },
        {
            "start_sec": 1.0,
            "end_sec": 2.0,
            "source_text": "First in source",
            "target_text": "",
        },
    ]

    result = apply_external_translation(cues, translated)

    assert [cue["target_text"] for cue in result] == [
        "剪辑后的第一句",
        "剪辑后的第二句",
    ]


def test_final_subtitle_timeline_uses_exact_authored_text(tmp_path):
    subtitle = tmp_path / "timeline.srt"
    subtitle.write_text(
        "1\n00:00:01,000 --> 00:00:02,500\n编辑后的字幕\n",
        encoding="utf-8",
    )

    cues = final_subtitle_timeline(subtitle)

    assert len(cues) == 1
    assert cues[0]["start_sec"] == 1.0
    assert cues[0]["end_sec"] == 2.5
    assert cues[0]["source_text"] == "编辑后的字幕"
    assert cues[0]["target_text"] == "编辑后的字幕"


def test_segment_cache_reuses_unchanged_render(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output = tmp_path / "output.mp4"
    cache_dir = tmp_path / "cache"
    segment = {
        "source_start_sec": 1.0,
        "source_end_sec": 3.0,
        "output_start_sec": 0.0,
        "output_end_sec": 2.0,
        "playback_rate": 1.0,
        "audio_mode": "source",
    }
    calls = []

    def fake_render_segment(**kwargs):
        calls.append(kwargs["segment"]["source_end_sec"])
        kwargs["output_path"].write_bytes(b"rendered")

    monkeypatch.setattr("render_story.render_segment", fake_render_segment)

    assert not restore_or_render_segment(
        ffmpeg="ffmpeg",
        source_video=source,
        segment=segment,
        output_path=output,
        source_has_audio=True,
        source_audio_stream=0,
        cache_dir=cache_dir,
    )
    output.unlink()
    assert restore_or_render_segment(
        ffmpeg="ffmpeg",
        source_video=source,
        segment=segment,
        output_path=output,
        source_has_audio=True,
        source_audio_stream=0,
        cache_dir=cache_dir,
    )

    assert calls == [3.0]
    assert output.read_bytes() == b"rendered"


def test_volume_keyframe_expression_interpolates_between_points():
    expression = build_volume_keyframe_expression(
        [
            {"time_sec": 0.0, "volume": 0.2},
            {"time_sec": 5.0, "volume": 1.0},
        ],
        duration=10.0,
        base_volume=0.5,
    )

    assert "between(t,0.000000,5.000000)" in expression
    assert "0.100000" in expression
    assert "0.500000" in expression


def test_narration_plan_accepts_default_background_volume():
    story_plan = {
        "job_id": "demo",
        "segments": [{"id": "seg-001", "output_end_sec": 10.0}],
    }
    evidence = {
        "job_id": "demo",
        "subtitles": [{"id": "sub-001"}],
        "scenes": [],
        "visual_candidates": [],
        "keyframes": [],
        "analysis_chunks": [],
    }
    analysis = {
        "job_id": "demo",
        "events": [{"id": "event-001"}],
        "themes": [],
        "visual_findings": [],
        "continuity_constraints": [],
        "story_options": [],
    }
    narration = {
        "schema_version": "1.0",
        "job_id": "demo",
        "style": "film_commentary",
        "settings": {"max_audio_speedup": 1.25},
        "tts": {
            "provider": "minimax",
            "voice_id": "female-shaonv",
            "speed": 1.0,
        },
        "blocks": [
            {
                "id": "nar-001",
                "start_sec": 0.0,
                "end_sec": 6.0,
                "text": "真正的变化发生在他作出决定之后。",
                "purpose": "建立转折。",
                "evidence_refs": ["event-001", "seg-001"],
            }
        ],
    }

    errors, warnings = validate_narration_plan(
        narration,
        story_plan,
        evidence,
        analysis,
    )

    assert errors == []
    assert warnings == []


def test_douyin_caption_is_normalized_and_counted():
    caption, length = validate_caption(
        "2026款丰田RAV4混动通勤实测：官方综合油耗41 MPG，实际跑出37.5 MPG。\n"
        "空间、车机和舒适性更成熟，但高速噪声与内饰用料仍有提升空间。"
    )

    assert "\n" not in caption
    assert 50 <= length <= 100


@pytest.mark.parametrize("caption", ["太短了", "A" * 60])
def test_douyin_caption_rejects_invalid_content(caption):
    with pytest.raises(ValueError):
        validate_caption(caption)


def test_douyin_hashtags_are_normalized_and_deduplicated():
    assert normalize_hashtags(["汽车评测, #混动SUV", "汽车评测", "丰田RAV4"]) == [
        "#汽车评测",
        "#混动SUV",
        "#丰田RAV4",
    ]


def _hybrid_commentary_inputs():
    story_plan = {
        "job_id": "film-demo",
        "segments": [{"id": "seg-001", "output_end_sec": 20.0}],
    }
    evidence = {
        "job_id": "film-demo",
        "subtitles": [{"id": "sub-001"}],
        "scenes": [],
        "visual_candidates": [],
        "keyframes": [],
        "analysis_chunks": [],
    }
    analysis = {
        "job_id": "film-demo",
        "events": [{"id": "event-001"}],
        "themes": [],
        "visual_findings": [],
        "continuity_constraints": [],
        "story_options": [],
    }
    narration = {
        "schema_version": "1.0",
        "job_id": "film-demo",
        "style": "film_commentary",
        "settings": {
            "audio_strategy": "hybrid_source_anchors",
            "original_audio_volume": 0.3,
            "source_audio_volume": 1.0,
            "max_audio_speedup": 1.25,
        },
        "tts": {
            "provider": "minimax",
            "voice_id": "female-shaonv",
            "speed": 1.0,
        },
        "blocks": [
            {
                "id": "nar-001",
                "start_sec": 0.0,
                "end_sec": 5.0,
                "text": "她以为这只是一次普通的重逢。",
                "purpose": "交代背景。",
                "evidence_refs": ["event-001", "seg-001"],
            },
            {
                "id": "nar-002",
                "start_sec": 11.0,
                "end_sec": 16.0,
                "text": "这句承诺让结局有了不同含义。",
                "purpose": "承接原声。",
                "evidence_refs": ["event-001", "seg-001"],
            },
        ],
        "source_audio_windows": [
            {
                "id": "src-001",
                "start_sec": 5.5,
                "end_sec": 9.5,
                "purpose": "保留人物作出承诺时的原声表演。",
                "evidence_refs": ["sub-001", "event-001", "seg-001"],
            }
        ],
    }
    return narration, story_plan, evidence, analysis


def test_hybrid_commentary_accepts_separated_source_audio_windows():
    narration, story_plan, evidence, analysis = _hybrid_commentary_inputs()

    errors, warnings = validate_narration_plan(
        narration,
        story_plan,
        evidence,
        analysis,
    )

    assert errors == []
    assert warnings == []


def test_english_narration_uses_word_rate_instead_of_character_rate():
    narration, story_plan, evidence, analysis = _hybrid_commentary_inputs()
    narration["blocks"][0]["text"] = (
        "Three years later, Rinko arrives in Paris to rebuild her career."
    )

    errors, _warnings = validate_narration_plan(
        narration,
        story_plan,
        evidence,
        analysis,
    )

    assert not any("narration is too dense" in error for error in errors)


def test_english_narration_rejects_excessive_word_rate():
    narration, story_plan, evidence, analysis = _hybrid_commentary_inputs()
    narration["blocks"][0]["text"] = (
        "Rinko returns to Paris and immediately begins explaining every detail "
        "of her long career while the entire kitchen waits for her final answer."
    )

    errors, _warnings = validate_narration_plan(
        narration,
        story_plan,
        evidence,
        analysis,
    )

    assert any("words/s" in error for error in errors)


def test_hybrid_commentary_rejects_narration_over_source_audio():
    narration, story_plan, evidence, analysis = _hybrid_commentary_inputs()
    narration["blocks"][1]["start_sec"] = 9.0

    errors, _warnings = validate_narration_plan(
        narration,
        story_plan,
        evidence,
        analysis,
    )

    assert any("overlaps narration block 'nar-002'" in error for error in errors)


def test_source_audio_subtitles_are_clipped_and_combined_with_narration():
    source_cues = [
        {
            "start_sec": 4.0,
            "end_sec": 7.0,
            "source_text": "約束する",
            "target_text": "我答应你。",
        },
        {
            "start_sec": 8.0,
            "end_sec": 12.0,
            "source_text": "必ず来る",
            "target_text": "我一定会来。",
        },
    ]
    windows = [{"id": "src-001", "start_sec": 5.5, "end_sec": 10.5}]
    narration_cues = [
        {
            "start_sec": 0.0,
            "end_sec": 4.5,
            "source_text": "",
            "target_text": "他终于给出了回答。",
        }
    ]

    selected = select_subtitle_cues_for_windows(source_cues, windows)
    combined = combine_commentary_subtitles(narration_cues, selected)

    assert [(cue["start_sec"], cue["end_sec"]) for cue in selected] == [
        (5.5, 7.0),
        (8.0, 10.5),
    ]
    assert [cue["target_text"] for cue in combined] == [
        "他终于给出了回答。",
        "我答应你。",
        "我一定会来。",
    ]


def test_source_volume_expression_restores_original_audio_in_anchor_window():
    expression = build_source_volume_expression(
        [{"start_sec": 5.5, "end_sec": 10.5}],
        background_volume=0.3,
        source_audio_volume=1.0,
    )

    assert "between(t,5.500000,10.500000)" in expression
    assert "1.000000,0.300000" in expression

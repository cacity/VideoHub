import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

FILM_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "videohub-film-commentary"
    / "scripts"
)
STORY_SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "videohub-story-editor"
    / "scripts"
)
sys.path.insert(0, str(FILM_SCRIPTS))
sys.path.insert(0, str(STORY_SCRIPTS))

from build_douyin_publish_package import ensure_qa_passed  # noqa: E402
from build_film_commentary_publish_package import (  # noqa: E402
    crop_to_vertical,
    render_vertical_cover,
    validate_publish_plan,
)


def sample_plan() -> dict:
    return {
        "schema_version": "1.0",
        "platform": "douyin",
        "selected_title": "丈夫卷走一千万，她被双重追捕",
        "title_candidates": [
            {
                "title": "丈夫卷走一千万，她被双重追捕",
                "angle": "背叛与追捕",
                "evidence_refs": ["event-004", "event-005"],
            },
            {
                "title": "最信任的人消失后，她只能独自逃生",
                "angle": "信任崩塌",
                "evidence_refs": ["event-004", "event-014"],
            },
            {
                "title": "刚躲过联邦探员，她又落进黑帮手里",
                "angle": "关键转折",
                "evidence_refs": ["event-011", "event-012"],
            },
        ],
        "caption": (
            "丈夫带着一千万美元突然消失，她被独自留在酒店，同时面对联邦探员和黑帮追捕。"
            "她只能靠伪装、谎言和父亲教过的生存技巧，一次次从包围中逃出去。"
        ),
        "hashtags": ["影视解说", "美剧", "悬疑剧", "犯罪剧"],
        "cover": {
            "timestamp_sec": 12.5,
            "focus_x": 0.55,
            "focus_y": 0.5,
            "layout": "bottom",
            "kicker": "10分钟看完",
            "headline": "丈夫卷款消失",
            "subheadline": "她被联邦探员和黑帮同时追杀",
            "episode_label": "《示例剧》S01E01",
        },
    }


def test_publish_plan_requires_evidence_backed_title_candidates():
    validated = validate_publish_plan(sample_plan())

    assert validated["selected_title"] == "丈夫卷走一千万，她被双重追捕"
    assert len(validated["title_candidates"]) == 3
    assert validated["hashtags"] == ["#影视解说", "#美剧", "#悬疑剧", "#犯罪剧"]
    assert 50 <= validated["caption_visible_chars"] <= 100


def test_publish_plan_rejects_selected_title_outside_candidates():
    plan = sample_plan()
    plan["selected_title"] = "不存在的标题候选"

    with pytest.raises(ValueError, match="标题候选"):
        validate_publish_plan(plan)


def test_qa_accepts_chinese_pass_marker(tmp_path: Path):
    report = tmp_path / "qa.md"
    report.write_text("- 结果：**PASS**\n", encoding="utf-8")

    ensure_qa_passed(report)


def test_render_vertical_cover_outputs_verified_9x16_image(tmp_path: Path):
    source = tmp_path / "source.jpg"
    output = tmp_path / "cover_9x16.jpg"
    image = Image.new("RGB", (1600, 900), (32, 44, 58))
    draw = ImageDraw.Draw(image)
    draw.rectangle((450, 80, 1150, 850), fill=(198, 155, 122))
    draw.ellipse((650, 160, 950, 460), fill=(230, 205, 176))
    image.save(source, quality=95)

    metrics = render_vertical_cover(
        source=source,
        output=output,
        config=sample_plan()["cover"],
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1080, 1920)
    assert metrics["width"] == 1080
    assert metrics["height"] == 1920
    assert metrics["luma_stddev"] >= 8
    assert output.stat().st_size > 10_000


def test_vertical_crop_treats_focus_as_subject_coordinate():
    image = Image.new("RGB", (2000, 1000), "red")
    ImageDraw.Draw(image).rectangle((1000, 0, 1999, 999), fill="blue")

    left_subject = crop_to_vertical(image, focus_x=0.2, focus_y=0.5)
    right_subject = crop_to_vertical(image, focus_x=0.8, focus_y=0.5)

    assert left_subject.getpixel((540, 960))[0] > 200
    assert right_subject.getpixel((540, 960))[2] > 200

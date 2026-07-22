from pathlib import Path


SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / ".agents"
    / "skills"
    / "videohub-film-commentary"
)


def test_skill_requires_traceable_web_plot_fact_checking():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference_text = (
        SKILL_DIR / "references" / "plot-research-and-fact-checking.md"
    ).read_text(encoding="utf-8")

    assert "plot-research-and-fact-checking.md" in skill_text
    assert "references/plot_research.md" in skill_text
    assert "不能替代字幕和画面证据" in skill_text
    assert "至少用两个相互独立的来源" in reference_text
    assert "默认避免引用后续集数的剧透" in skill_text

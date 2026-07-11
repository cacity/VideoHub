"""Structured helpers for parsing and rebuilding ASS/SSA subtitle events."""

from collections import OrderedDict
from dataclasses import dataclass
import re
from typing import Iterable, List, Optional


DEFAULT_ASS_EVENT_FIELDS = (
    "Layer",
    "Start",
    "End",
    "Style",
    "Name",
    "MarginL",
    "MarginR",
    "MarginV",
    "Effect",
    "Text",
)

TARGET_STYLE_NAMES = {
    "secondary",
    "target",
    "translation",
    "translated",
    "chinese",
    "zh",
    "中文",
    "译文",
    "次要",
}


@dataclass
class AssDialogue:
    line_index: int
    leading_whitespace: str
    fields: List[str]
    values: List[str]
    start: str
    end: str
    style: str
    text: str
    start_seconds: float
    end_seconds: float

    def rebuild(self, text: Optional[str] = None) -> str:
        values = list(self.values)
        text_index = self.fields.index("text")
        if text is not None:
            values[text_index] = text
        return f"{self.leading_whitespace}Dialogue: {','.join(values)}"


def ass_time_to_seconds(value: str) -> float:
    """Convert ASS H:MM:SS.cc timestamps to seconds."""
    parts = (value or "").strip().replace(",", ".").split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid ASS timestamp: {value}")
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_ass_dialogues(content: str) -> List[AssDialogue]:
    """Parse Dialogue events while respecting the active ASS Events Format line."""
    dialogues: List[AssDialogue] = []
    event_fields = [field.lower() for field in DEFAULT_ASS_EVENT_FIELDS]
    in_events = False

    for line_index, line in enumerate(content.splitlines()):
        stripped = line.strip().lstrip("\ufeff")
        if stripped.startswith("[") and stripped.endswith("]"):
            in_events = stripped.lower() == "[events]"
            continue
        if not in_events:
            continue

        if stripped.lower().startswith("format:"):
            parsed_fields = [
                field.strip().lower()
                for field in stripped.split(":", 1)[1].split(",")
                if field.strip()
            ]
            if {"start", "end", "text"}.issubset(parsed_fields):
                event_fields = parsed_fields
            continue

        if not stripped.lower().startswith("dialogue:"):
            continue

        payload = stripped.split(":", 1)[1].lstrip()
        values = payload.split(",", max(len(event_fields) - 1, 0))
        if len(values) != len(event_fields):
            continue

        try:
            start_index = event_fields.index("start")
            end_index = event_fields.index("end")
            text_index = event_fields.index("text")
            style_index = event_fields.index("style") if "style" in event_fields else None
            start = values[start_index].strip()
            end = values[end_index].strip()
            start_seconds = ass_time_to_seconds(start)
            end_seconds = ass_time_to_seconds(end)
        except (ValueError, IndexError):
            continue

        leading_whitespace = line[: len(line) - len(line.lstrip())]
        dialogues.append(
            AssDialogue(
                line_index=line_index,
                leading_whitespace=leading_whitespace,
                fields=list(event_fields),
                values=values,
                start=start,
                end=end,
                style=values[style_index].strip() if style_index is not None else "",
                text=values[text_index],
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        )

    return dialogues


def group_ass_dialogues(dialogues: Iterable[AssDialogue]) -> List[List[AssDialogue]]:
    """Group events by their exact start/end timeline while retaining source order."""
    groups = OrderedDict()
    for dialogue in dialogues:
        key = (dialogue.start, dialogue.end)
        groups.setdefault(key, []).append(dialogue)
    return list(groups.values())


def clean_ass_text(text: str) -> str:
    """Remove ASS override tags and convert hard-space/line markers to readable text."""
    value = re.sub(r"\{[^{}]*\}", "", text or "")
    value = re.sub(r"\\[Nn]", "\n", value)
    value = value.replace(r"\h", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return " ".join(line for line in lines if line).strip()


def escape_ass_text(text: str) -> str:
    """Escape translated plain text for use in an ASS Dialogue Text field."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r", "")
        .replace("\n", r"\N")
        .strip()
    )


def _language_family(language_code: str) -> str:
    code = (language_code or "").replace("_", "-").lower()
    if code in {"zh", "chi", "zho", "cmn"} or code.startswith("zh-"):
        return "zh"
    return code.split("-")[0]


def ass_text_language_score(text: str, target_language: str) -> int:
    """Return a script-based confidence score that text is already in the target language."""
    value = clean_ass_text(text)
    if not value:
        return 0

    family = _language_family(target_language)
    patterns = {
        "zh": r"[\u4e00-\u9fff]",
        "ja": r"[\u3040-\u30ff]",
        "ko": r"[\uac00-\ud7af]",
        "ru": r"[\u0400-\u04ff]",
        "ar": r"[\u0600-\u06ff]",
    }
    pattern = patterns.get(family)
    if pattern:
        return len(re.findall(pattern, value))

    if family == "en" and not re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff]", value):
        return len(re.findall(r"[A-Za-z]", value))
    return 0


def target_style_score(style: str) -> int:
    normalized = (style or "").strip().lower()
    return 1 if normalized in TARGET_STYLE_NAMES else 0


def choose_ass_dialogue_for_tts(
    dialogues: List[AssDialogue],
    target_language: str = "zh-CN",
) -> Optional[AssDialogue]:
    """Choose the translated line from a bilingual timeline group for TTS."""
    if not dialogues:
        return None
    return max(
        dialogues,
        key=lambda item: (
            ass_text_language_score(item.text, target_language),
            target_style_score(item.style),
            -item.line_index,
        ),
    )

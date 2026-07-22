"""Generate cached MiniMax voice samples and a local comparison page."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.minimax_tts_client import DEFAULT_MODEL, MiniMaxTTSClient  # noqa: E402


DEFAULT_TEXT = (
    "丈夫带着一千万美元突然消失，Lucky 被独自留在酒店。"
    "楼下是联邦探员，门外还有黑帮的人。"
    "她深吸一口气，因为从这一刻开始，她只能靠自己逃出去。"
)

VOICE_SAMPLES = [
    {
        "name": "播报男声",
        "voice_id": "Chinese (Mandarin)_Male_Announcer",
        "group": "男声",
        "usage": "剧情梳理、新闻感解说",
    },
    {
        "name": "电台男主播",
        "voice_id": "Chinese (Mandarin)_Radio_Host",
        "group": "男声",
        "usage": "播客串讲、自然叙述",
    },
    {
        "name": "温润男声",
        "voice_id": "Chinese (Mandarin)_Gentleman",
        "group": "男声",
        "usage": "治愈、人物故事",
    },
    {
        "name": "沉稳高管",
        "voice_id": "Chinese (Mandarin)_Reliable_Executive",
        "group": "男声",
        "usage": "悬疑、商业、成熟叙事",
    },
    {
        "name": "抒情男声",
        "voice_id": "Chinese (Mandarin)_Lyrical_Voice",
        "group": "男声",
        "usage": "情感、文艺、回忆段落",
    },
    {
        "name": "真诚青年",
        "voice_id": "Chinese (Mandarin)_Sincere_Adult",
        "group": "男声",
        "usage": "生活化解说、轻剧情",
    },
    {
        "name": "新闻女声",
        "voice_id": "Chinese (Mandarin)_News_Anchor",
        "group": "女声",
        "usage": "信息密集、清晰讲解",
    },
    {
        "name": "阅历姐姐",
        "voice_id": "Chinese (Mandarin)_Wise_Women",
        "group": "女声",
        "usage": "人物关系、家庭与成长",
    },
    {
        "name": "成熟女性",
        "voice_id": "female-chengshu",
        "group": "女声",
        "usage": "成熟叙事、剧情解说",
    },
    {
        "name": "御姐",
        "voice_id": "female-yujie",
        "group": "女声",
        "usage": "悬疑、都市、强情绪",
    },
    {
        "name": "温暖闺蜜",
        "voice_id": "Chinese (Mandarin)_Warm_Bestie",
        "group": "女声",
        "usage": "生活、情感、陪伴感叙述",
    },
    {
        "name": "甜美女性",
        "voice_id": "female-tianmei",
        "group": "女声",
        "usage": "轻松、短视频、年轻题材",
    },
]


@dataclass
class SampleResult:
    index: int
    name: str
    voice_id: str
    group: str
    usage: str
    status: str
    filename: str = ""
    duration_seconds: float = 0.0
    sample_rate: int = 0
    error: str = ""


def valid_wav(path: Path) -> tuple[bool, float, int]:
    if not path.is_file() or path.stat().st_size < 44:
        return False, 0.0, 0
    try:
        with wave.open(str(path), "rb") as audio:
            rate = audio.getframerate()
            frames = audio.getnframes()
            duration = frames / rate if rate else 0.0
        return duration > 0.5, duration, rate
    except (wave.Error, OSError):
        return False, 0.0, 0


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff-]+", "_", value).strip("_")
    return cleaned or "voice"


def render_index(
    output_dir: Path,
    results: list[SampleResult],
    model: str,
    speed: float,
    text: str,
) -> None:
    successful = [item for item in results if item.status in {"generated", "cached"}]
    rows = []
    for item in successful:
        rows.append(
            f"""
            <tr>
              <td><strong>{item.index:02d}. {html.escape(item.name)}</strong><br>
                <span class="muted">{html.escape(item.group)}</span></td>
              <td><audio controls preload="none" src="{html.escape(item.filename)}"></audio></td>
              <td>{html.escape(item.usage)}</td>
              <td><code>{html.escape(item.voice_id)}</code></td>
              <td>{item.duration_seconds:.1f} 秒</td>
            </tr>"""
        )

    failures = [item for item in results if item.status == "failed"]
    failure_html = ""
    if failures:
        failure_items = "".join(
            f"<li>{html.escape(item.name)}：{html.escape(item.error)}</li>"
            for item in failures
        )
        failure_html = f"<section class=\"failures\"><h2>生成失败</h2><ul>{failure_items}</ul></section>"

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MiniMax 中文音色试听</title>
  <style>
    :root {{ color-scheme: light; --ink:#202326; --muted:#67717b; --line:#d8dde2;
      --surface:#f5f7f8; --accent:#0b6b50; --warn:#a33a2b; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: #fff; font: 15px/1.55 system-ui,
      "Microsoft YaHei", sans-serif; }}
    header {{ border-bottom: 1px solid var(--line); background: var(--surface); }}
    header div, main {{ width: min(1220px, calc(100% - 32px)); margin: 0 auto; }}
    header div {{ padding: 24px 0 20px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 6px 0; }}
    main {{ padding: 22px 0 40px; }}
    .meta {{ color: var(--muted); }}
    .sample-text {{ margin: 18px 0; padding: 14px 16px; border-left: 4px solid var(--accent);
      background: var(--surface); border-radius: 0 4px 4px 0; }}
    .table-wrap {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; }}
    table {{ width: 100%; min-width: 980px; border-collapse: collapse; }}
    th, td {{ padding: 12px; text-align: left; vertical-align: middle;
      border-bottom: 1px solid var(--line); }}
    th {{ background: var(--surface); font-size: 13px; }}
    tr:last-child td {{ border-bottom: 0; }}
    audio {{ width: 290px; height: 36px; }}
    code {{ white-space: normal; overflow-wrap: anywhere; color: var(--accent); }}
    .muted {{ color: var(--muted); font-size: 13px; }}
    .failures {{ color: var(--warn); }}
    @media (max-width: 640px) {{
      header div, main {{ width: min(100% - 20px, 1220px); }}
      h1 {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <header><div>
    <h1>MiniMax 中文音色试听</h1>
    <p class="meta">模型：{html.escape(model)} · 语速：{speed:.1f} · 成功音色：{len(successful)}</p>
  </div></header>
  <main>
    <p>所有音色使用同一段文案。建议戴耳机比较咬字、停顿、情绪和长时间收听是否疲劳。</p>
    <div class="sample-text"><strong>统一测试文案</strong><br>{html.escape(text)}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>音色</th><th>试听</th><th>建议场景</th><th>Voice ID</th><th>时长</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    {failure_html}
  </main>
</body>
</html>
"""
    (output_dir / "index.html").write_text(page, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default=DEFAULT_TEXT, help="所有音色共用的中文试听文案")
    parser.add_argument("--model", default=None, help="默认读取 MINIMAX_TTS_MODEL")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="忽略有效缓存并重新生成")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    model = args.model or os.getenv("MINIMAX_TTS_MODEL") or DEFAULT_MODEL
    text_hash = hashlib.sha1(args.text.encode("utf-8")).hexdigest()[:12]
    output_dir = args.output_dir or (
        REPO_ROOT
        / "workspace"
        / "dubbing_temp"
        / "voice_previews"
        / "minimax_comparison"
        / safe_filename(model)
        / text_hash
    )
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    client = MiniMaxTTSClient(
        model=model,
        voice_id=VOICE_SAMPLES[0]["voice_id"],
        speed=args.speed,
        language_boost="Chinese",
    )
    results: list[SampleResult] = []
    for index, voice in enumerate(VOICE_SAMPLES, start=1):
        filename = f"{index:02d}_{safe_filename(voice['name'])}.wav"
        target = output_dir / filename
        valid, duration, sample_rate = valid_wav(target)
        if valid and not args.force:
            print(f"[{index:02d}/{len(VOICE_SAMPLES)}] 缓存：{voice['name']}")
            results.append(
                SampleResult(index, **voice, status="cached", filename=filename,
                             duration_seconds=duration, sample_rate=sample_rate)
            )
            continue

        print(f"[{index:02d}/{len(VOICE_SAMPLES)}] 生成：{voice['name']}", flush=True)
        client.voice_id = voice["voice_id"]
        try:
            client.synthesize(args.text, target)
            valid, duration, sample_rate = valid_wav(target)
            if not valid:
                raise RuntimeError("返回的 WAV 文件无法解码或时长过短")
            results.append(
                SampleResult(index, **voice, status="generated", filename=filename,
                             duration_seconds=duration, sample_rate=sample_rate)
            )
        except Exception as exc:  # Keep the rest of the comparison set usable.
            print(f"  失败：{exc}", file=sys.stderr, flush=True)
            results.append(SampleResult(index, **voice, status="failed", error=str(exc)))

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": model,
        "speed": args.speed,
        "language_boost": "Chinese",
        "sample_text": args.text,
        "text_sha1": hashlib.sha1(args.text.encode("utf-8")).hexdigest(),
        "output_dir": str(output_dir),
        "results": [asdict(item) for item in results],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    render_index(output_dir, results, model, args.speed, args.text)

    success_count = sum(item.status in {"generated", "cached"} for item in results)
    print(f"完成：{success_count}/{len(results)} 个音色可试听")
    print(f"试听页面：{output_dir / 'index.html'}")
    return 0 if success_count else 1


if __name__ == "__main__":
    raise SystemExit(main())

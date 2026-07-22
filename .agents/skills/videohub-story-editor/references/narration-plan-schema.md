# Narration Plan 1.0

`narration_plan.json` 定义解说版的中文叙述、时间位置、证据来源和 TTS 配置。
它不修改 `story_plan.json` 的剪辑范围，原声版与解说版因此可以复用同一套画面和
来源映射。

## 结构

```json
{
  "schema_version": "1.0",
  "job_id": "video-slug_20260720_120000",
  "story_plan_path": "story_plan.json",
  "style": "film_commentary",
  "settings": {
    "target_language": "zh-CN",
    "audio_strategy": "hybrid_source_anchors",
    "original_audio_volume": 0.3,
    "source_audio_volume": 1.0,
    "max_audio_speedup": 1.25
  },
  "tts": {
    "provider": "minimax",
    "model": "speech-2.8-turbo",
    "voice_id": "female-shaonv",
    "speed": 1.0,
    "language_boost": "Chinese"
  },
  "blocks": [
    {
      "id": "nar-001",
      "start_sec": 0.5,
      "end_sec": 8.0,
      "text": "他以为这只是一次普通的选择，却没有意识到真正的转折已经发生。",
      "subtitle_text": "他以为这只是一次普通的选择，却没有意识到真正的转折已经发生。",
      "purpose": "建立悬念并交代转折。",
      "evidence_refs": ["event-001", "seg-001"]
    }
  ],
  "source_audio_windows": [
    {
      "id": "src-001",
      "start_sec": 8.2,
      "end_sec": 13.6,
      "purpose": "保留人物作出关键选择时的原声表演。",
      "evidence_refs": ["sub-018", "seg-002", "event-003"]
    }
  ]
}
```

## 叙述规则

- 先读完整 `story_analysis.json`、`story_plan.json` 和来源映射，再写解说。
- `text` 只能陈述证据可以支持的事实；推断、评价或过渡语不能伪装成原片对白。
- 每个块至少引用一个真实证据 ID 或剪辑片段 ID。
- 时间使用最终成片时间轴，块之间不能重叠，也不能超过成片时长。
- 一般控制在每秒 3 到 5 个中文字符；超过每秒 6.5 个字符会校验失败。
- 优先重写过长文案，不依赖明显加速。允许的自动加速上限由
  `max_audio_speedup` 控制，默认 1.25 倍。
- 重要原声对白前后留出空白，让观众可以听清原片；不要让解说填满整条时间轴。
- `subtitle_text` 可以为适合屏幕阅读的精简版本；省略时使用 `text`。

## 旁白与原声混合

- `audio_strategy=narration_only`：默认兼容模式，不使用 `source_audio_windows`。
- `audio_strategy=hybrid_source_anchors`：影视剧解说模式，要求至少一个
  `source_audio_windows` 条目。
- `source_audio_windows` 使用最终成片时间轴，不能互相重叠，也不能与任何旁白块重叠。
- 原声窗口默认恢复到 `source_audio_volume=1.0`；其他区域按
  `original_audio_volume=0.3` 混入原片声音。
- 单个原声窗口建议 2-10 秒；超过 20 秒会警告，超过 30 秒会校验失败。
- 原声总占比低于 3% 或高于 20%会警告。影视解说通常保持旁白主导，只把不可替代的
  冲突、转折、告白、反问、笑点或告别留给原声。
- 外语原声窗口必须提供最终时间轴译文；渲染器可将原声字幕与旁白字幕合并并烧录为
  中文或双语字幕。

## style

只允许：

- `film_commentary`：影视解说。
- `drama_recap`：短剧或剧情回顾。
- `documentary_commentary`：纪录片式解说。
- `podcast_recap`：播客观点串讲。
- `knowledge_explainer`：课程、演讲或教程解读。

## TTS 配置

MiniMax 示例：

```json
{
  "provider": "minimax",
  "model": "speech-2.8-turbo",
  "voice_id": "female-shaonv",
  "speed": 1.0,
  "language_boost": "Chinese"
}
```

豆包示例：

```json
{
  "provider": "doubao",
  "voice_type": "BV701_streaming",
  "speed": 1.0,
  "volume": 1.0,
  "pitch": 1.0,
  "sample_rate": 24000
}
```

API Key、AppID 和 Access Token 只能通过环境变量或本地 `.env` 提供，不能写入
计划、日志或 Git 仓库。切换供应商只改 `tts.provider` 及对应音色字段，不改变
解说块和剪辑计划。

## 校验与产物

校验：

```powershell
python .agents/skills/videohub-story-editor/scripts/validate_narration_plan.py `
  "<job_dir>/narration_plan.json" `
  --story-plan "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json"
```

合成脚本输出：

- `narration_audio_<provider>.wav`：与成片时间轴对齐的完整旁白轨。
- `narration_<provider>.srt`：跟随实际语音时长的中文字幕。
- `narration_audio_<provider>.json`：音色、时长、缓存命中和证据引用清单。
- `.narration_cache/<provider>/`：分段 TTS 缓存，文案与配置不变时复用。

MiniMax 或豆包不可用时，只让解说版失败；已经完成的证据包、剪辑计划、后置翻译
和原声版不得受影响。

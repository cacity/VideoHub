# Film Commentary Plan Extension

影视剧解说复用 `videohub-story-editor` 的 `narration_plan.json`，只增加混合音频字段。

```json
{
  "schema_version": "1.0",
  "job_id": "film-demo",
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
    "voice_id": "Chinese (Mandarin)_Male_Announcer",
    "speed": 1.0,
    "language_boost": "Chinese"
  },
  "blocks": [
    {
      "id": "nar-001",
      "start_sec": 0.3,
      "end_sec": 6.8,
      "text": "她把这次见面当作普通告别，却不知道对方已经作出了最后决定。",
      "purpose": "交代原声前的最低背景。",
      "evidence_refs": ["event-003", "seg-001"]
    }
  ],
  "source_audio_windows": [
    {
      "id": "src-001",
      "start_sec": 7.2,
      "end_sec": 12.6,
      "purpose": "保留人物亲口作出承诺时的表演和停顿。",
      "evidence_refs": ["sub-038", "sub-039", "event-004", "seg-002"]
    }
  ]
}
```

## 约束

- `audio_strategy` 必须为 `hybrid_source_anchors`。
- `style` 使用 `film_commentary` 或 `drama_recap`。
- `blocks` 和 `source_audio_windows` 都使用最终成片时间轴。
- 旁白块、原声窗口内部各自按时间排序，且彼此不能重叠。
- 每个原声窗口必须填写 `id`、`start_sec`、`end_sec`、`purpose` 和
  `evidence_refs`。
- 原声窗口不能超过成片时长；单段超过 20 秒会警告，超过 30 秒失败。
- 原声总占比低于 3% 或高于 20%会警告。
- `original_audio_volume` 和 `source_audio_volume` 都在 0-1 之间。

渲染器根据窗口动态调整原片音量，并从最终原文/译文字幕中截取窗口内对白，与 TTS
字幕按时间合并。原声字幕不得使用重排前的时间码。

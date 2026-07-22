# Story Plan 1.0

## 目录

- 草案结构
- 文件结构
- 字段约束
- 时间轴规则
- 最小示例

## 草案结构

模型只生成 `story_plan.draft.json`，不要计算输出时间轴或 FFmpeg 命令：

```json
{
  "schema_version": "1.0-draft",
  "job_id": "video-slug_20260720_120000",
  "settings": {
    "target_duration_sec": 240.0,
    "duration_tolerance_ratio": 0.15,
    "target_language": "zh-CN",
    "subtitle_mode": "bilingual",
    "translation_stage": "post_edit",
    "translation_polish": true,
    "allow_speed_change": false
  },
  "selected_option_id": "option-01",
  "segments": [
    {
      "id": "seg-001",
      "kind": "dialogue",
      "story_role": "hook",
      "source_start_sec": 615.2,
      "source_end_sec": 630.8,
      "source_subtitle_ids": ["sub-00188", "sub-00189"],
      "analysis_refs": ["arc-001", "event-004"],
      "playback_rate": 1.0,
      "audio_mode": "source",
      "story_reason": "直接给出故事的关键变化。",
      "transition": "cut"
    }
  ]
}
```

`compile_story_plan.py` 根据证据包补全场景引用、字幕文本、输出时间轴和输出路径，
生成下面的正式计划。

## 文件结构

`story_plan.json` 是成片的唯一剪辑依据。所有时间使用秒，保留最多三位小数。

```json
{
  "schema_version": "1.0",
  "job_id": "video-slug_20260720_120000",
  "evidence_pack_path": "workspace/review_packs/story_editor/example/evidence_pack.json",
  "story_analysis_path": "workspace/review_packs/story_editor/example/story_analysis.json",
  "source": {
    "video_path": "workspace/youtube/example.mp4",
    "fingerprint": "sha256-derived-source-fingerprint",
    "duration_sec": 1800.0,
    "language": "en"
  },
  "settings": {
    "target_duration_sec": 240.0,
    "duration_tolerance_ratio": 0.15,
    "target_language": "zh-CN",
    "subtitle_mode": "bilingual",
    "translation_stage": "post_edit",
    "translation_polish": true,
    "allow_speed_change": false
  },
  "classification": {
    "type": "podcast_interview",
    "secondary_type": null,
    "confidence": 0.91,
    "evidence_refs": ["sub-00001", "sub-00035", "chunk-002"],
    "evidence": [
      "两位说话者以长轮次问答为主",
      "画面长期保持固定机位",
      "字幕结构包含连续问题和回答"
    ]
  },
  "story": {
    "selected_option_id": "option-01",
    "premise": "嘉宾解释一次失败如何改变了他的产品判断。",
    "angle": "从失败切入，最后回到可复用的方法。",
    "arc": ["hook", "context", "development", "turn", "resolution"]
  },
  "segments": [],
  "output": {
    "video_path": "workspace/videos_with_subtitles/example_story_240s.mp4",
    "source_subtitle_path": "story_source.srt",
    "translated_subtitle_path": "story_zh-CN.srt",
    "bilingual_subtitle_path": "story_bilingual.ass",
    "qa_report_path": "story_qa.md"
  }
}
```

## 字段约束

### classification.type

只允许：

`drama`、`podcast_interview`、`documentary`、`speech`、`tutorial`、`news_commentary`、`vlog`、`music_performance`、`mixed`。

### settings.subtitle_mode

只允许：

- `none`：不输出字幕。
- `source`：只输出原文。
- `translated`：只输出译文。
- `bilingual`：原文与译文同时输出。

外文转中文默认 `bilingual`。

### settings.translation_stage

只允许：

- `post_edit`：推荐。先根据原文字幕完成理解、选段和重排，再重建成片原文 SRT，
  最后翻译这份成片字幕。这样翻译上下文和时间轴都以最终叙事顺序为准。
- `pre_edit`：兼容已有证据包中的逐句译文，适合已经完成翻译的旧任务。
- `none`：不生成译文。

`translation_polish` 为 `true` 时，成片字幕翻译后尝试使用 DeepSeek 做轻度全局润色。
没有配置 DeepSeek Key 时必须保留基础翻译，不能阻断故事剪辑和原声版输出。

### segments

每个片段结构：

```json
{
  "id": "seg-001",
  "output_order": 1,
  "kind": "dialogue",
  "story_role": "hook",
  "source_start_sec": 615.2,
  "source_end_sec": 630.8,
  "output_start_sec": 0.0,
  "output_end_sec": 15.6,
  "playback_rate": 1.0,
  "source_subtitle_ids": ["sub-188", "sub-189"],
  "source_scene_ids": ["scene-0042"],
  "analysis_refs": ["arc-001", "event-004"],
  "source_text": "I realized we had solved the wrong problem.",
  "target_text": "我意识到，我们解决错了问题。",
  "speaker": "Guest",
  "audio_mode": "source",
  "story_reason": "直接给出故事的关键变化，适合作为开场。",
  "transition": "cut"
}
```

字段规则：

- `id`：任务内唯一。
- `output_order`：从 1 开始连续递增。
- `kind`：`dialogue` 或 `visual`。
- `story_role`：`hook`、`context`、`development`、`turn`、`resolution`、`closing`。
- `source_start_sec`、`source_end_sec`：必须位于源视频范围内，结束大于开始。
- `output_start_sec`、`output_end_sec`：按成片顺序递增。
- `playback_rate`：默认 1.0，允许 0.5–2.0。`allow_speed_change` 为 `false` 时必须为 1.0；不要仅为凑整时长改变对白速度。
- `source_subtitle_ids`：对白片段不能为空；视觉片段应为空。
- `source_scene_ids`：片段覆盖的原片场景；视觉片段至少引用一个场景。
- `analysis_refs`：至少引用一个 `story_analysis.json` 中的分析节点。
- `source_text`：对白原文。视觉片段使用空字符串。
- `target_text`：译文。`translation_stage=post_edit`、无需翻译或视觉片段时可为空；
  后置翻译由 `translate_story_subtitles.py` 生成，再通过渲染器注入最终时间轴。
- `speaker`：已知时填写；视觉片段可为空。
- `audio_mode`：`source`、`mute`、`duck`、`narration`。
- `story_reason`：解释该片段对故事的具体作用，不能为空。
- `transition`：确定性 v1 渲染只使用 `cut`。`fade`、`crossfade` 是保留值，
  在渲染器明确支持前不得用于正式成片。

当 `audio_mode` 为 `narration` 时，额外提供：

```json
{
  "narration_text": "三个月后，他重新回到这个问题。",
  "narration_source": "editorial_bridge"
}
```

旁白不能冒充原片对白，必须在字幕和来源映射中标记为编辑内容。

## 时间轴规则

- 默认片段输出时长约等于 `(source_end_sec - source_start_sec) / playback_rate`。
- 片段边界应留足完整发音，不机械贴着字幕时间裁切；可按波形向前后扩 0.1–0.4 秒。
- 输出时间轴必须连续。使用交叉淡化时，显式记录重叠后的输出时间。
- 原字幕与片段相交时裁切到片段范围，再换算到输出时间轴。
- 一个原字幕条目被多个片段使用时，来源映射必须分别记录。
- 成片字幕最后时间不得超过成片时长。

## 最小示例

```json
{
  "schema_version": "1.0",
  "job_id": "demo",
  "evidence_pack_path": "evidence_pack.json",
  "story_analysis_path": "story_analysis.json",
  "source": {
    "video_path": "demo.mp4",
    "fingerprint": "demo-fingerprint",
    "duration_sec": 1800,
    "language": "zh"
  },
  "settings": {
    "target_duration_sec": 60,
    "duration_tolerance_ratio": 0.15,
    "target_language": "zh-CN",
    "subtitle_mode": "source",
    "translation_stage": "none",
    "translation_polish": false,
    "allow_speed_change": false
  },
  "classification": {
    "type": "speech",
    "secondary_type": null,
    "confidence": 0.8,
    "evidence_refs": ["sub-001", "sub-080", "chunk-001"],
    "evidence": ["单人连续表达", "结构包含主张和例证", "固定讲台画面"]
  },
  "story": {
    "selected_option_id": "option-01",
    "premise": "讲者用一个例子解释为什么先验证问题。",
    "angle": "从常见错误切入，最后给出解决方法。",
    "arc": ["hook", "context", "resolution"]
  },
  "segments": [
    {
      "id": "seg-001",
      "output_order": 1,
      "kind": "dialogue",
      "story_role": "hook",
      "source_start_sec": 10,
      "source_end_sec": 40,
      "output_start_sec": 0,
      "output_end_sec": 30,
      "playback_rate": 1,
      "source_subtitle_ids": ["sub-001"],
      "source_scene_ids": ["scene-001"],
      "analysis_refs": ["arc-001", "event-001"],
      "source_text": "我们最容易犯的错误，是急着解决一个还没有验证的问题。",
      "target_text": "",
      "speaker": "讲者",
      "audio_mode": "source",
      "story_reason": "直接提出核心问题。",
      "transition": "cut"
    },
    {
      "id": "seg-002",
      "output_order": 2,
      "kind": "dialogue",
      "story_role": "resolution",
      "source_start_sec": 300,
      "source_end_sec": 330,
      "output_start_sec": 30,
      "output_end_sec": 60,
      "playback_rate": 1,
      "source_subtitle_ids": ["sub-080"],
      "source_scene_ids": ["scene-020"],
      "analysis_refs": ["arc-003", "event-003"],
      "source_text": "先用最小成本验证，再决定是否投入。",
      "target_text": "",
      "speaker": "讲者",
      "audio_mode": "source",
      "story_reason": "给出可执行结论。",
      "transition": "cut"
    }
  ],
  "output": {
    "video_path": "demo_story_60s.mp4",
    "source_subtitle_path": "demo_story.srt",
    "translated_subtitle_path": null,
    "bilingual_subtitle_path": null,
    "qa_report_path": "demo_story_qa.md"
  }
}
```

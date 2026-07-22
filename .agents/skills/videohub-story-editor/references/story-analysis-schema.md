# Story Analysis 1.0

`story_analysis.json` 是证据层与剪辑计划之间的模型输出。Codex、Claude Code、DeepSeek
或其他模型都必须返回同一结构，并使用证据 ID 支撑判断。

## 分析顺序

1. 逐个读取 `evidence_pack.json` 中的 `analysis_chunks`。
2. 为每个分块记录内容摘要、事件、观点、人物和未解决的指代。
3. 检查关键帧时填写视觉发现；未实际查看画面时不得推测画面内容。
4. 汇总全片时间线、因果关系、主题和连续性约束。
5. 提出一到三个可剪辑故事方案，选定一个方案后再生成剪辑计划。

长视频不得只把完整字幕一次性提交给模型后直接选段。分块结论必须保留
`sub-*`、`scene-*`、`frame-*`、`visual-*` 或 `chunk-*` 引用。

## 文件结构

```json
{
  "schema_version": "1.0",
  "job_id": "example_20260720_120000",
  "evidence_pack_path": "workspace/review_packs/story_editor/example/evidence_pack.json",
  "content_profile": {
    "type": "podcast_interview",
    "secondary_type": null,
    "confidence": 0.91,
    "evidence_refs": ["sub-00001", "sub-00035", "chunk-002"]
  },
  "global_summary": "嘉宾复盘产品失败，并解释判断方式如何改变。",
  "chunk_findings": [],
  "entities": [],
  "events": [],
  "themes": [],
  "visual_findings": [],
  "continuity_constraints": [],
  "story_options": [],
  "selected_option_id": "option-01",
  "uncertainties": []
}
```

## 主要字段

### content_profile

- `type`：使用 `story-plan-schema.md` 中的内容类型。
- `confidence`：0 到 1。低于 0.65 时使用 `mixed`。
- `evidence_refs`：至少三个证据引用，不能只引用标题或文件名。

### chunk_findings

每个分析分块对应一项：

```json
{
  "id": "finding-001",
  "chunk_id": "chunk-001",
  "summary": "主持人提出失败是否来自错误需求的问题。",
  "speaker_or_character_updates": ["嘉宾首次解释项目背景"],
  "open_questions": ["“第二次尝试”尚未说明结果"],
  "evidence_refs": ["sub-00001", "sub-00002", "frame-0001"]
}
```

### entities

```json
{
  "id": "entity-001",
  "name": "嘉宾",
  "kind": "speaker",
  "role": "主要叙述者",
  "aliases": ["SPEAKER_01"],
  "evidence_refs": ["sub-00003"]
}
```

字幕没有可靠说话人信息时，使用“说话者 A”等中性名称，不根据声音或画面猜测真实身份。

### events

事件也可表示播客中的观点节点或教程步骤：

```json
{
  "id": "event-001",
  "label": "发现需求判断错误",
  "kind": "event",
  "chronology_index": 3,
  "summary": "团队发现解决的问题并非用户真正需要的问题。",
  "cause_event_ids": ["event-000"],
  "evidence_refs": ["sub-00188", "sub-00189"],
  "confidence": 0.94
}
```

`kind` 允许 `event`、`claim`、`question`、`answer`、`step`、`result`。因果关系不明确时，
`cause_event_ids` 使用空数组，不得把时间先后自动写成因果。

### themes

```json
{
  "id": "theme-001",
  "label": "先验证问题再投入",
  "summary": "不同案例共同支持先验证真实需求。",
  "evidence_refs": ["sub-00042", "sub-00190"]
}
```

### visual_findings

只有实际检查过关键帧或原片画面后才能填写：

```json
{
  "id": "visual-finding-001",
  "summary": "嘉宾停顿后露出明显犹豫，适合作为转折反应镜头。",
  "frame_refs": ["frame-0008"],
  "scene_refs": ["scene-0042"],
  "candidate_refs": ["visual-0003"],
  "confidence": 0.78
}
```

### continuity_constraints

```json
{
  "id": "constraint-001",
  "type": "pronoun",
  "description": "“这个决定”必须放在介绍取消旧方案之后。",
  "required_before_refs": ["sub-00110"],
  "protected_refs": ["sub-00112"]
}
```

`type` 允许 `chronology`、`causality`、`pronoun`、`speaker`、`location`、`tutorial_order`、
`question_answer`、`visual_reaction`。

### story_options

```json
{
  "id": "option-01",
  "premise": "一次失败如何改变嘉宾验证产品需求的方式。",
  "angle": "从失败切入，最后回到可复用的方法。",
  "estimated_duration_sec": 240,
  "target_audience": "对产品开发感兴趣的普通观众",
  "arc": [
    {
      "id": "arc-001",
      "role": "hook",
      "purpose": "先展示结论最反直觉的部分。",
      "evidence_refs": ["sub-00188", "sub-00189"]
    }
  ],
  "risks": ["开场先给结论，需要随后补足项目背景。"]
}
```

`selected_option_id` 必须引用一个真实方案。剪辑计划中的 `analysis_refs` 应引用选中方案的
`arc-*`、`event-*`、`theme-*`、`constraint-*` 或 `visual-finding-*` ID。

## 不确定性

信息不足或画面未检查时，写入：

```json
{
  "id": "uncertainty-001",
  "description": "无法仅凭字幕确认两段对白是否发生在同一地点。",
  "evidence_refs": ["sub-00070", "sub-00092"],
  "impact": "重排前必须检查对应场景画面。"
}
```

不能用模型推测填补证据缺口。

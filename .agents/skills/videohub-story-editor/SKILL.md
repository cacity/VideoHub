---
name: videohub-story-editor
description: 把长视频或已有字幕转成有完整叙事的几分钟短片。先基于原文字幕和画面证据理解、选段与重排，再对最终时间轴重新翻译和可选润色；既可输出保留原声的双语字幕版，也可把原声降到 30% 并用 MiniMax 或豆包 TTS 生成影视解说、短剧混剪、播客串讲或知识解读版，还可整理为带 50-100 字中文文案的抖音发布包。用于“把长视频讲成短故事”“按字幕自动剪辑”“剪好后再翻译”“制作 TTS 解说版”“生成抖音发布文件夹和文案”等任务。
---

# VideoHub Story Editor

使用以下固定结构，不直接让模型凭摘要调用 FFmpeg：

```text
视频和原文字幕
  -> 证据提取层
  -> 故事理解层
  -> 剪辑规划层
  -> 最终原文时间轴
  -> 后置翻译和可选润色
  -> 原声版 / TTS 解说版
  -> 确定性渲染和 QA
  -> 抖音发布包（可选）
```

## 边界

- 不安装或调用 WhisperX。
- 优先使用人工字幕或平台字幕；缺少字幕时，调用 `videohub-youtube` 和
  `src/youtube_transcriber.py` 的现有 Whisper 流程。
- 故事理解和选段以原文字幕为证据。不要依赖剪辑前的逐句机翻决定剧情、因果或
  说话人意图。
- 模型负责理解、选段和撰写解说；脚本负责时间计算、证据校验、翻译接入、TTS
  对齐、渲染和 QA。
- 原声版和解说版必须复用同一个 `story_plan.json`，避免两套版本选段漂移。
- 翻译或 TTS 凭据缺失时，不得阻断证据提取、故事计划和原声原文版。
- 默认先交付分析与剪辑方案；用户明确要求成片后才执行渲染。
- 只处理用户有权下载和再创作的内容。

## 默认值

- 目标时长：240 秒，容差 15%。
- 输出语言：简体中文。
- 外文视频：剪辑后翻译，原声版默认双语字幕。
- 解说版：中文 TTS 字幕，原声音量 0.30。
- 播放速度：1.0 倍，不为凑时长自动改变原片对白速度。
- 分析目录：`workspace/review_packs/story_editor/<job_id>/`。
- 成片目录：`workspace/videos_with_subtitles/` 或计划中的输出目录。
- 抖音发布包：`workspace/publish_packages/douyin/<package_name>/`。

## 1. 证据提取层

确认视频和带时间码的原文字幕存在。没有字幕时先使用 VideoHub 现有字幕流程。

```powershell
python .agents/skills/videohub-story-editor/scripts/build_evidence_pack.py `
  --video "<video_path>" `
  --subtitle "<source_subtitle.srt>" `
  --language "<source_language>" `
  --target-language "zh-CN"
```

新任务默认不要传 `--translated-subtitle`。该参数只用于兼容已经有可靠译文的旧任务。
脚本输出 `evidence_pack.json`、`transcript.json`、`scenes.json`、关键帧和
`analysis_chunks/chunk-*.json`。

场景检测或抽帧成本过高时可使用 `--skip-scene-detection` 或 `--skip-keyframes`，
但必须在分析的不确定性中说明视觉证据缺失。

## 2. 故事理解层

读取 [story-analysis-schema.md](references/story-analysis-schema.md) 和
[editing-strategies.md](references/editing-strategies.md)。

1. 逐个读取 `analysis_chunks`，记录人物或说话人、事件、观点、问题、答案、步骤和结果。
2. 实际检查关键帧后再填写视觉发现；未看画面时不得猜测动作、表情或地点。
3. 汇总全片时间线、因果关系、主题、指代和连续性约束。
4. 提出一到三个故事方案，选择一个方案。
5. 所有结论保留 `sub-*`、`scene-*`、`frame-*`、`visual-*` 或 `chunk-*` 引用。

Codex、Claude Code 或 DeepSeek 都必须写出同一数据契约的 `story_analysis.json`。
调用 API 模型时，按 [model-workflow.md](references/model-workflow.md) 分批提交证据，
不要让供应商响应格式进入后续脚本。

```powershell
python .agents/skills/videohub-story-editor/scripts/validate_story_analysis.py `
  "<job_dir>/story_analysis.json" `
  --evidence "<job_dir>/evidence_pack.json"
```

有错误时不得进入剪辑规划。

## 3. 剪辑规划层

根据选中的故事方案创建 `story_plan.draft.json`。读取
[story-plan-schema.md](references/story-plan-schema.md)，外文视频默认设置：

```json
{
  "subtitle_mode": "bilingual",
  "translation_stage": "post_edit",
  "translation_polish": true
}
```

每个片段填写 `kind`、`story_role`、源时间范围、`analysis_refs`、
`story_reason`、`audio_mode` 和 `transition`。对白片段优先显式列出
`source_subtitle_ids`。允许重排，但不能改变事实、因果、教程步骤、问题与回答关系，
或拼出说话者没有表达过的观点。

```powershell
python .agents/skills/videohub-story-editor/scripts/compile_story_plan.py `
  "<job_dir>/story_plan.draft.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json" `
  --output "<job_dir>/story_plan.json"

python .agents/skills/videohub-story-editor/scripts/validate_story_plan.py `
  "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json"
```

同时交付 `story_outline.md` 和 `story_source_map.csv` 供人工审核。校验错误必须修正；
警告必须解释或修正。

## 4. 剪辑后翻译

先按最终选段和重排顺序重建原文 SRT：

```powershell
python .agents/skills/videohub-story-editor/scripts/prepare_story_subtitles.py `
  "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json" `
  --output "<job_dir>/final_source.srt"
```

再翻译最终 SRT。`translation_polish=true` 或显式 `--polish` 时，复用 VideoHub
现有的 Google 基础翻译和 DeepSeek 全局轻度润色，并保留可对比的基础翻译与润色版。

```powershell
python .agents/skills/videohub-story-editor/scripts/translate_story_subtitles.py `
  "<job_dir>/story_plan.json" `
  --source "<job_dir>/final_source.srt" `
  --output "<job_dir>/final_zh-CN.srt" `
  --polish
```

没有 `DEEPSEEK_API_KEY` 时自动跳过润色并保留基础翻译；翻译失败也不能破坏已经生成的
原文字幕、故事计划或源视频。脚本生成 `post_edit_translation.json` 记录实际状态。

## 5. 原声版

原声版保留原片声音，并把剪辑后翻译注入最终时间轴：

```powershell
python .agents/skills/videohub-story-editor/scripts/render_story.py `
  "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json" `
  --translated-subtitle "<job_dir>/final_zh-CN.srt" `
  --burn-subtitles bilingual `
  --subtitle-prefix "<job_dir>/source_audio" `
  --output "<output_dir>/<name>_source_audio.mp4" `
  --qa-report "<job_dir>/source_audio_qa.md"
```

`--burn-subtitles` 允许 `none`、`source`、`translated`、`bilingual`。外文视频烧录
译文或双语字幕时，必须提供覆盖全部最终字幕条目的后置翻译。

## 6. TTS 解说版

读取 [narration-plan-schema.md](references/narration-plan-schema.md)，根据完整故事分析、
剪辑计划和来源映射撰写 `narration_plan.json`。解说可以串联和概括选中内容，但每个
叙述块都必须引用证据，不能虚构原片没有提供的事实。

电影、电视剧或短剧需要“第三者旁白为主、关键场面恢复影视原声”时，改用
`videohub-film-commentary` Skill。它仍复用本流程，但会增加不与旁白重叠的
`source_audio_windows`、动态原声音量和合并字幕。

```powershell
python .agents/skills/videohub-story-editor/scripts/validate_narration_plan.py `
  "<job_dir>/narration_plan.json" `
  --story-plan "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json"
```

MiniMax 使用 `MINIMAX_API_KEY`；豆包使用 `DOUBAO_TTS_APP_ID`、
`DOUBAO_TTS_ACCESS_TOKEN`，可选 `DOUBAO_TTS_RESOURCE_ID`。凭据只放在本地环境变量
或 `.env`，不要写进 JSON。

```powershell
python .agents/skills/videohub-story-editor/scripts/synthesize_story_narration.py `
  "<job_dir>/narration_plan.json" `
  --story-plan "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json"
```

合成器按文案和音色缓存分段 WAV，校验实际时长，生成与最终成片对齐的完整旁白轨和
中文字幕。然后渲染解说版：

```powershell
python .agents/skills/videohub-story-editor/scripts/render_story.py `
  "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json" `
  --narration-audio "<job_dir>/narration_audio_minimax.wav" `
  --narration-subtitle "<job_dir>/narration_minimax.srt" `
  --background-volume 0.30 `
  --burn-subtitles translated `
  --subtitle-prefix "<job_dir>/narration_minimax" `
  --output "<output_dir>/<name>_narration_minimax.mp4" `
  --qa-report "<job_dir>/narration_minimax_qa.md"
```

豆包版本将文件名中的 `minimax` 换成 `doubao`。默认把原声降到 30%，但保留环境声、
音乐和关键对白。叙述文本过长时先改写；只有在不超过计划上限时才自动轻度加速。

## 7. 确定性渲染和交付

渲染器必须：

- 只接受校验通过且来源指纹一致的计划。
- 按原片时间范围重新编码片段并按 `output_order` 拼接。
- 根据片段交集裁切原字幕，并换算到重排后的输出时间轴。
- 分别输出原声版和解说版字幕、成片及 QA 报告，不互相覆盖。
- 完整解码成片，检查时长和字幕边界；QA 通过后才清理中间片段。
- 不删除源视频、证据包、计划和 TTS 缓存。

确定性 v1 渲染器只执行 `cut`。`fade` 和 `crossfade` 必须在渲染器明确支持后再用于
正式计划。

至少交付：

- `evidence_pack.json`
- `story_analysis.json`
- `story_plan.json`
- `story_outline.md`
- `story_source_map.csv`
- 原声版 MP4、最终原文/译文/双语字幕和 QA 报告
- 请求解说版时，再交付 `narration_plan.json`、TTS 音轨、中文字幕、解说版 MP4 和 QA 报告

## 8. 抖音发布包

用户要求“适合发到抖音的文件夹”“发布包”或“配一段发布文案”时，在成片 QA 通过后
生成发布包。先根据 `story_analysis.json`、最终解说稿和实际成片撰写 50-100 个可见字符
的中文文案：概括具体内容和看点，不虚构结论，不使用与视频无关的夸张标题；话题标签
单独保存，不用标签凑文案长度。

```powershell
python .agents/skills/videohub-story-editor/scripts/build_douyin_publish_package.py `
  "<final_video.mp4>" `
  --title "<发布标题>" `
  --caption "<50-100字中文文案>" `
  --hashtag "<话题1>" `
  --hashtag "<话题2>" `
  --source-url "<source_url>" `
  --qa-report "<job_dir>/qa.md" `
  --cover-time <representative_second>
```

发布包至少包含：

- 经过媒体探测的 H.264/AAC MP4；已符合要求时优先硬链接，避免重复占用空间。
- `caption.txt`：仅保存 50-100 字正文。
- `hashtags.txt`：独立保存建议话题。
- `cover.jpg`：用户要求或有合适代表画面时生成。
- `publish_notes.md`：供人工发布前检查。
- `publish_manifest.json`：记录媒体参数、文案长度、来源、QA 报告和 SHA-256。

横版成片默认保持原构图和 1080P，不自动强裁为竖屏。用户明确要求竖版时，应先重新
设计画面布局并完成单独 QA，不能直接裁掉人物、字幕或关键物体。发布前仍需人工检查
平台规则、版权授权、标题、封面和字幕。

不得把重排前的字幕时间码直接复制到成片。每个成片片段、原声字幕和解说块都必须
能回溯到原视频时间范围或证据 ID。

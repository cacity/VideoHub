---
name: videohub-story-editor
description: 把长视频或已有字幕转成有完整叙事的几分钟短片。先基于原文字幕和画面证据理解、选段与重排，再对最终时间轴重新翻译和可选润色；既可输出保留原声的双语字幕版，也可把原声降到 30% 并用 MiniMax 或豆包 TTS 生成影视解说、短剧混剪、播客串讲或知识解读版。已有项目可进入本地五轨时间线继续调整切点、旁白、原声窗口、字幕、音量和转场，并按修订版本渲染。用于“把长视频讲成短故事”“按字幕自动剪辑”“剪好后再翻译”“制作 TTS 解说版”“可视化精修”“生成抖音发布文件夹和文案”等任务。
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

## 剧集素材项目目录

用户只提供一个剧集目录时，不再要求分别提供视频和字幕路径。先刷新目录内的可移植项目清单：

```powershell
python src/series_project.py "<series_dir>"
```

读取 `<series_dir>/videohub_project.json`，按用户给出的集数或文件名选择 `episodes` 中的条目。
视频位于项目根目录；本地批处理生成的字幕位于 `subtitles/`。选择字幕时依次优先使用：

1. `subtitles.polished` 中的 SRT。
2. `subtitles.translated` 中与目标语言匹配的 SRT。
3. `subtitles.source` 中的 SRT。
4. 视频内嵌字幕；仍没有字幕时再调用 VideoHub Whisper 流程。

清单只保存相对路径，移动整个剧集目录后仍可使用。空格、下划线、连字符以及
`_google`、`_polished`、语言后缀的差异由项目扫描器归一化匹配。目录包含多集而用户未说明
集数时，必须先确认目标集，不能默认把整季当成一个视频任务。

## 可视化时间线精修

已有解说项目完成 AI 初剪后，可以启动本地网页工作台：

```powershell
cd frontend
npm install
npm run build
cd ..
python src/story_timeline_server.py
```

打开 `http://127.0.0.1:8766/story-editor`，选择包含
`docs/story_job/story_plan.json` 的 `workspace/projectNNN_*` 项目。工作台导入故事计划、
旁白计划、字幕和证据文件，显示视频、原声、TTS 旁白、原声锚点和字幕五条轨道。

- 可以预览素材，拖动切点，拆分、删除和重排片段，并撤销或重做。
- 可以修改旁白文本、单独调用 MiniMax 重生成一个语音块，拖动原声窗口和字幕边界；
  预览画面中的解说字幕可上下拖动，避开原片已有的硬字幕，保存后按同一位置烧录。
- 可以设置片段音量关键帧、淡入淡出、交叉转场，并注册其他本地视频源。
- 配置 `DEEPSEEK_API_KEY` 后可以对选中的旁白做保守局部改写；缺少密钥时不影响其他功能。
- 保存会写入项目的 `revisions/rev-*`；片段缓存写入 `.story_editor_cache/segments`。
  不覆盖源视频、原始计划、原始字幕或已有 TTS 文件。

时间线编辑器是人工精修入口。对剧情、人物和因果的判断仍应先执行下面的证据提取与故事
理解流程，不能用拖动时间线替代证据校验。

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

`source_subtitle_ids` 是剧情证据引用，不保证覆盖片段里的全部对白。影视解说需要在底部
持续显示完整原声字幕时，渲染器必须使用 `--source-subtitle-policy all-intersecting`，按每个
入选片段的源时间范围收集并裁切全部相交字幕。默认 `explicit` 保持证据引用模式，兼容已有
计划。

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

当前渲染器支持普通切换和 `crossfade`，也支持片段级视频/音频淡入淡出、音量关键帧、
片段缓存以及多个本地视频源。多个来源会统一到主视频的分辨率和帧率后再拼接。旧计划中的
`fade` 转场不会被当作独立转场类型；需要淡入淡出时，应设置片段的 `fade_in_sec` 和
`fade_out_sec`。

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

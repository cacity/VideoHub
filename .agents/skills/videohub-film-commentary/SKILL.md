---
name: videohub-film-commentary
description: 把电影、电视剧或短剧素材制作成第三者旁白主导、关键影视原声点睛的中文解说视频，并生成抖音竖版封面、标题候选、50-100 字文案、话题和完整发布包。复用 videohub-story-editor 的证据提取、剧情理解、剪辑、后置翻译、TTS 与字幕流程，并可联网校验片名、人物关系和剧情背景，为冲突、转折、告白、反问、笑点、承诺与告别设计不与旁白重叠的原声锚点。用于“影视解说”“电影解说”“剧情讲述”“第三者旁白加原片台词”“保留演员原声做混剪”“制作影视解说封面和抖音发布物料”等任务。
---

# VideoHub Film Commentary

先读取 `videohub-story-editor/SKILL.md`，本 Skill 只增加影视剧专用的讲述策略和
旁白/原声混合规则，不复制基础流水线。

片名为《东京大饭店》或 `Grand Maison Tokyo` 时，必须读取并执行
[tokyo-grand-maison-production-preset.md](references/tokyo-grand-maison-production-preset.md)。

处理连续剧后续集、要求“沿用上一集规格”或批量制作多集时，必须读取
[series-episode-production.md](references/series-episode-production.md)，先继承上一集可验证的制作参数，
再按当前集素材重新建立剧情证据和剪辑计划。新建批量项目还必须读取
[series-job-schema.md](references/series-job-schema.md)，使用 `scripts/run_series_commentary.py`
统一执行预检、计划、渲染、发布包和审计；不得在项目目录继续复制通用生产代码。

用户只提供剧集目录时，先执行 `videohub-story-editor` 的“剧集素材项目目录”流程，读取目录内
的 `videohub_project.json` 自动定位当前集视频和最佳字幕，不再要求用户重复提供字幕路径。

## 默认成片

- 目标时长沿用用户要求；未指定时使用 240 秒。
- 第三者旁白主导，原声锚点通常占成片 5%-12%。剧情高度依赖对白时可提高，但超过
  20% 必须解释。
- 旁白区原片声音为 0.30；原声锚点恢复到 1.00。
- 单个原声锚点优先为 2-10 秒，默认保留 4-8 个；不能为了凑比例保留普通对白。
- 外语原声必须有中文或双语字幕。旁白字幕只显示实际播出的解说词。
- 完成影视解说成片后默认生成抖音发布包，包括 1080x1920 封面、3-5 个标题候选、
  已选标题、50-100 字文案和 3-8 个话题；用户明确不要时才省略。
- 每期成片默认生成章节信息。通常按剧情转折划分 4-7 章，同时提供带起止时间和内容说明的
  `chapters.md`，以及可直接粘贴到平台的 `chapters.txt`。
- 只处理用户有权下载、剪辑和发布的素材。

## 1. 理解完整剧情

按 `videohub-story-editor` 建立 `evidence_pack.json` 和 `story_analysis.json`。影视剧分析
必须额外明确：

- 主要人物、关系、欲望、阻碍、秘密和认知变化。
- 引发后续结果的关键选择，而不只是按时间罗列事件。
- 可重排的信息与不能倒置的因果、悬念、身份揭示和情绪积累。
- 角色声音、表情、沉默或环境声不可被旁白替代的表演时刻。

不要根据剪辑前机翻决定人物动机。先使用原文字幕和画面证据理解，再完成选段和重排。

### 1.1 联网剧情校验

读取 [plot-research-and-fact-checking.md](references/plot-research-and-fact-checking.md)。用户明确
要求联网，或片名、集数、人物译名、人物关系、时代背景、字幕含义存在歧义时，必须先检索
可靠资料进行交叉核验，并把查询词、来源、链接、访问日期、被核验事实和可信度写入当前项目
的 `references/plot_research.md`。

联网资料只是辅助校验层，不能替代字幕和画面证据。具体到本集发生了什么、角色在何时做了
什么、某段能否被剪入成片，必须以用户提供的视频、原文字幕和实际画面为准。网络梗概与本地
素材冲突时，优先采用本地素材；无法消解的冲突写入 `story_analysis.json` 的 `uncertainties`，
不得用推测补齐剧情。默认避免引用后续集数的剧透。

## 2. 设计第三者旁白

读取 [narration-and-source-audio.md](references/narration-and-source-audio.md)。旁白用于：

- 快速交代人物、关系、处境、时间跨度和必要文化背景。
- 压缩重复对话、行动过程、支线与低信息场景。
- 在场景跳跃之间补足因果，让观众知道“为什么下一幕会发生”。
- 在转折之后解释其影响，但不要抢在表演之前替角色下结论。

使用具体动词和可验证事实。第三者视角可以解释，但不能把推测写成角色真实想法，也
不能把解说者观点伪装成原片台词。

## 3. 选择影视原声

只在“声音和表演本身比信息摘要更重要”时保留原声：

- 角色第一次显露核心性格或关系张力。
- 决定、拒绝、揭露、反问、告白、承诺、和解或告别。
- 演员停顿、哭泣、笑声、呼吸和环境声共同完成情绪的场面。
- 反复出现的主题句、关键笑点或结局回响。

不要保留只负责解释设定、重复旁白、信息密度低、收音差或无法可靠翻译的对白。原声
前用旁白提供最低限度上下文，原声结束后留 0.3-1.0 秒反应或环境声，再恢复旁白。

## 4. 编写混合解说计划

读取 [film-commentary-plan-schema.md](references/film-commentary-plan-schema.md)。在
`narration_plan.json` 中设置：

```json
{
  "style": "film_commentary",
  "settings": {
    "audio_strategy": "hybrid_source_anchors",
    "original_audio_volume": 0.3,
    "source_audio_volume": 1.0
  },
  "blocks": [],
  "source_audio_windows": []
}
```

旁白块和原声窗口全部使用最终成片时间轴，二者不能重叠。每个条目必须说明叙事用途并
引用真实字幕、画面、事件或剪辑片段证据。

```powershell
python .agents/skills/videohub-film-commentary/scripts/validate_commentary_plan.py `
  "<job_dir>/narration_plan.json" `
  --story-plan "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json"
```

校验错误必须修正。原声比例、单段长度等警告必须解释或调整。

## 5. 后置翻译、TTS 和渲染

先按最终剪辑时间轴生成原文字幕，再翻译和可选 DeepSeek 轻度润色。为旁白生成对齐的
MiniMax 或豆包 TTS，然后把同一 `narration_plan.json` 传给渲染器：

首次选择 MiniMax 音色或用户要求比较音色时，使用统一文案批量生成带缓存的试听页：

```powershell
python .agents/skills/videohub-film-commentary/scripts/generate_minimax_voice_samples.py
```

输出位于 `workspace/dubbing_temp/voice_previews/minimax_comparison/`。同一模型、文案和音色
已有有效 WAV 时直接复用；`index.html` 用同一段解说词并列比较男声、女声、播报、抒情和
生活化音色。不能只根据几秒样片决定整片音色，正式生成前还应抽取 30-60 秒真实旁白检查
长句停顿、情绪一致性和听觉疲劳。

```powershell
python .agents/skills/videohub-story-editor/scripts/render_story.py `
  "<job_dir>/story_plan.json" `
  --evidence "<job_dir>/evidence_pack.json" `
  --analysis "<job_dir>/story_analysis.json" `
  --translated-subtitle "<job_dir>/final_zh-CN.srt" `
  --narration-plan "<job_dir>/narration_plan.json" `
  --narration-audio "<job_dir>/narration_audio_minimax.wav" `
  --narration-subtitle "<job_dir>/narration_minimax.srt" `
  --burn-subtitles bilingual `
  --output "<output_dir>/<name>_film_commentary.mp4" `
  --qa-report "<job_dir>/film_commentary_qa.md"
```

中文原片可省略 `--translated-subtitle`。外语原声烧录中文或双语字幕时必须提供覆盖
最终原文时间轴的译文。覆盖范围是所有入选视频片段中实际保留、可听见的外语对白，不能只
检查恢复到 100% 音量的关键原声窗口。必须按全部入选片段执行严格覆盖检查，明确口语对白
缺失数必须为 0。完整解码、字幕边界和时长 QA 通过后才能交付。

AI 初剪和首次渲染完成后，如需人工调整片段切点、旁白块、原声锚点或字幕，使用
`videohub-story-editor` 的本地五轨时间线工作台。所有调整保存为项目内独立修订，并复用
未变化片段和旁白缓存；不要直接覆盖本 Skill 生成的原始故事计划与 TTS 资产。

## 6. 生成抖音封面和发布物料

封面必须调用 `videohub-cover-designer`，由该 Skill 统一处理剧名、集数徽标、人物焦点、
四种画幅和主页缩略图检查；不要在每个项目里重新复制一套封面脚本。

成片 QA 通过后，读取
[douyin-publish-plan-schema.md](references/douyin-publish-plan-schema.md)，结合
`story_analysis.json`、最终旁白和实际成片编写 `publish_plan.json`。

- 提供 3-5 个角度不同的标题候选，并选出一个主标题。每个候选都引用真实事件或剪辑证据。
- 封面使用实际影视画面，不生成与演员、服装或场景不一致的 AI 剧照。
- 选择清晰的人物近景、关系对峙或关键转折帧；尽量避开黑场、模糊、血腥特写和无关字幕。
- 横版成片只为封面生成 1080x1920 竖版构图，不强制把完整视频裁成竖版。
- 封面标题比发布标题更短，控制为一眼能读完的主标题和副标题，文字避开人物眼睛与表情。
- 连续剧封面必须让剧名和集数在个人主页小缩略图中仍可辨认。默认同时输出 9:16、3:4、
  4:3、16:9；集数使用高对比、大字号独立标记，不能依赖小号副标题表达。
- 文案为 50-100 个可见中文字符，话题为 3-8 个；标题、封面和文案不能泄露成片没有
  讲到的情节，也不能夸大为真实事件、禁播或完整结局。

```powershell
python .agents/skills/videohub-film-commentary/scripts/build_film_commentary_publish_package.py `
  "<film_commentary.mp4>" `
  --plan "<job_dir>/publish_plan.json" `
  --qa-report "<job_dir>/film_commentary_qa.md" `
  --cover-source "<optional_clean_video.mp4>"
```

脚本输出 `cover_9x16.jpg`、`titles.txt`、`caption.txt`、`hashtags.txt`、发布视频、
`publish_notes.md`、原始 `publish_plan.json` 和带媒体/封面校验信息的
`publish_manifest.json`。必须打开封面和至少抽查一张发布视频画面，确认人物裁切、文字换行、
字幕、标题事实和抖音安全区后才能交付。

连续剧项目完成后运行统一审计；外语剧必须传入全片段对白覆盖报告：

```powershell
python .agents/skills/videohub-film-commentary/scripts/audit_series_episode.py `
  "<project_dir>" `
  --video "outputs/<final>.mp4" `
  --package "outputs/douyin_delivery" `
  --expected-duration <seconds> `
  --coverage-report "docs/story_job/source_dialogue_coverage.json" `
  --full-decode `
  --json-out "docs/series_episode_audit.json"
```

时长、流规格、全片段外语对白覆盖、封面尺寸、发布包视频哈希、SHA-256 清单或完整解码任一
失败时，不得标记完成。

## 7. 交付

除基础故事剪辑产物外，至少交付：

- `narration_plan.json`，包含旁白块和原声锚点。
- TTS 音轨及实际时长字幕。
- 合并后的旁白/原声字幕。
- 原声动态混音成片和 QA 报告。
- `publish_plan.json`、1080x1920 竖版封面、标题候选、已选标题、50-100 字文案、话题和
  完整抖音发布包。
- `chapters.md` 和 `chapters.txt`。章节边界必须使用最终成片时间轴，优先落在场景、目标、
  冲突或叙事阶段真正发生变化的位置；通常划分 4-7 章，不按固定分钟机械等分。每章标题
  应在小空间内可读，内容说明概括该段主要人物、冲突和结果，不泄露成片未讲到的剧情。

不要用旁白覆盖原声锚点，不要用原声承担大段剧情交代，也不要把样本中的具体比例当成
所有题材的硬指标。喜剧、悬疑、爱情、家庭剧和动作片应根据表演价值调整节奏。

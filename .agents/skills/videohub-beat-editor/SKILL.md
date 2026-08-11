---
name: videohub-beat-editor
description: 根据一段音频、歌曲或参考视频的节拍，为一个长视频、多个视频或素材目录自动建立镜头候选库，生成卡点剪辑计划，并批量渲染 16:9、3:4、4:3、9:16 等多画幅成片。支持固定镜头数量、强拍切换、歌词字幕、镜头替换、封面、标题、caption、hashtags 和完整 QA。用于“按音乐卡点剪视频”“给音频和素材批量做卡点视频”“检测强拍并自动选镜头”“同一计划输出多个画幅”等任务。
---

# VideoHub Beat Editor

把音频节拍、素材筛选和确定性渲染分开处理：

```text
音频或参考视频
  -> 节拍、强拍和乐句边界
  -> 固定帧数的切点计划
视频或素材目录
  -> 全片抽帧、质量评分和相似画面去重
  -> 人工复核候选联系表
  -> 镜头编排
  -> 多画幅批量渲染
  -> 歌词字幕、封面和发布文字
  -> 完整解码与逐切点 QA
```

## 核心原则

- 音频决定成片长度和每段帧数，视频素材只填充镜头。
- 正式计划中的总帧数必须等于 `round(audio_duration * fps)`。
- 替换镜头时只改来源和中心时间，不改变该段 `frames`。
- 自动评分只生成草案；正式渲染前必须查看候选和入选联系表。
- 避免连续使用高度相似的航拍、同一主体或同一运动方向。
- 只有用户提供歌词、可靠字幕或明确要求转写时才烧录歌词；不要凭听感编造。
- 不混入素材视频原声，除非用户明确要求。
- 只处理用户有权使用的音频和视频素材。

## 1. 创建独立任务目录

按仓库 SOP 创建 `workspace/projectNNN_project_name/`，至少包含：

```text
data/  docs/  outputs/  work/  logs/
```

输入较大时优先建立硬链接；不要复制数 GB 素材。所有计划和输出必须留在任务目录。

## 2. 分析音频

音频、带音轨视频均可作为输入：

```powershell
python .agents/skills/videohub-beat-editor/scripts/analyze_audio.py `
  --audio "<audio_or_reference_video>" `
  --output-dir "<job_dir>" `
  --clip-count 23 `
  --fps 30
```

不指定 `--clip-count` 时可使用 `--beats-per-cut 1` 或 `2`。先试听
`outputs/beat_click_preview.wav`，确认点击声落在期望强拍上，再继续。

## 3. 建立视频候选库

支持单视频、重复 `--video` 或素材目录：

```powershell
python .agents/skills/videohub-beat-editor/scripts/build_video_catalog.py `
  --cut-plan "<job_dir>/outputs/beat_plan.json" `
  --video "<long_video.mp4>" `
  --video-dir "<optional_material_dir>" `
  --output-dir "<job_dir>" `
  --sample-interval 20
```

检查：

- `outputs/all_candidates_*.jpg`
- `outputs/selected_candidates.jpg`
- `outputs/video_catalog.csv`
- `docs/edit_plan.draft.json`

把草案复制为 `docs/edit_plan.json` 后才能正式渲染。按构图和顺序调整
`source_center_sec`、`focus_x`、`focus_y`；详细字段见
[plan-schema.md](references/plan-schema.md)。

## 4. 批量渲染

```powershell
python .agents/skills/videohub-beat-editor/scripts/render_beat_batch.py `
  --plan "<job_dir>/docs/edit_plan.json" `
  --output-dir "<job_dir>/outputs/final" `
  --ratio 16:9 `
  --ratio 3:4 `
  --ratio 4:3 `
  --subtitle "<optional_lyrics.ass>" `
  --name "beat_edit"
```

每个画幅独立进行中心裁切。人物或地标不在中央时，在计划中设置 `focus_x`、
`focus_y`，不要直接强裁主体。

## 5. 歌词、封面和发布包

- 歌词字幕优先使用 ASS；中文和外语分两行，放在平台安全区。
- 3:4、4:3 封面优先使用真实入选镜头，不生成与成片无关的场景。
- 标题提供 3 个候选；caption 保持 50-100 个中文可见字符；hashtags 单独保存。
- 发布文字必须能从成片镜头得到支持，不夸大地点、季节或拍摄方式。

## 6. QA

渲染脚本必须为每个输出生成 QA JSON 和 Markdown，至少确认：

- 时长与音频相差不超过一帧。
- 帧数、分辨率、比例、H.264/AAC 正确。
- 完整解码无错误。
- 所有计划切点前后存在明显画面差异。
- 歌词三段分别抽帧检查字形、位置和遮挡。
- 多画幅预览没有裁掉人物、地标或字幕。

QA 未通过时不得把文件标记为成品。

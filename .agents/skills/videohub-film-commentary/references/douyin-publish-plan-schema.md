# 影视解说抖音发布计划

完成成片和 QA 后编写 `publish_plan.json`。标题和封面文案必须来自最终成片已经讲清楚的
剧情，不得用未进入成片的支线、错误人物关系或虚构悬念吸引点击。

```json
{
  "schema_version": "1.0",
  "platform": "douyin",
  "package_name": "lucky_s01e01_10min",
  "video_name": "Lucky_S01E01_10分钟影视解说",
  "selected_title": "丈夫卷走一千万，她被FBI和黑帮同时追杀",
  "title_candidates": [
    {
      "title": "丈夫卷走一千万，她被FBI和黑帮同时追杀",
      "angle": "背叛与双重追捕",
      "evidence_refs": ["event-004", "event-005", "event-013"]
    },
    {
      "title": "最信任的人带钱消失，她只能独自逃出追杀",
      "angle": "信任崩塌与自救",
      "evidence_refs": ["event-004", "event-014"]
    },
    {
      "title": "FBI刚要抓住她，黑帮却先一步把人劫走",
      "angle": "停车区追捕转折",
      "evidence_refs": ["event-011", "event-012"]
    }
  ],
  "caption": "丈夫带着一千万美元突然消失，Lucky 被独自留在酒店，同时面对 FBI 和黑帮追捕。她只能靠伪装、谎言和父亲教过的生存技巧，一次次从包围中逃出去。",
  "hashtags": ["影视解说", "美剧", "悬疑剧", "犯罪剧", "Lucky"],
  "source_url": "",
  "cover": {
    "timestamp_sec": 360.0,
    "focus_x": 0.5,
    "focus_y": 0.5,
    "layout": "bottom",
    "kicker": "10分钟看完",
    "headline": "丈夫卷款消失",
    "subheadline": "她被FBI和黑帮同时追杀",
    "episode_label": "《Lucky》S01E01"
  }
}
```

## 标题

- 写 3-5 个互不重复的标题候选，每个 8-38 个可见字符。
- 候选分别从核心冲突、人物选择、关键转折等角度切入，不要只替换同义词。
- 每个候选填写 `angle` 和真实 `evidence_refs`；`selected_title` 必须与其中一个候选一致。
- 不虚构人物死亡、身份、关系、金额或结局，不使用“全网禁播”“真实事件”等无证据措辞。
- 标题负责说明冲突，封面只保留更短的视觉钩子，不要把完整标题重复贴到封面。

## 封面

- 固定输出 1080x1920 JPEG，使用成片或原片的真实代表帧，不生成与人物不一致的 AI 剧照。
- 优先选择人物近景、关系对峙或行动转折；避免模糊帧、黑场、片尾、血腥特写和正在显示
  无关歌词/字幕的画面。
- `focus_x`、`focus_y` 位于 0-1，用于控制横版画面裁成竖版时的视觉中心。
- `layout` 根据人物位置选择 `top` 或 `bottom`，让文字避开眼睛和主要表情。
- `kicker` 2-12 字，`headline` 4-20 字，`subheadline` 不超过 28 字。三者必须是成片事实，
  不得堆叠多个感叹号或无意义煽动词。
- 生成后必须打开 `cover_9x16.jpg` 人工检查人物裁切、文字换行、对比度和抖音界面安全区。

## 文案与话题

- `caption` 为 50-100 个可见中文字符，交代人物处境、核心冲突和观看价值；不要逐段复述。
- 话题 3-8 个，独立保存；作品名、题材和内容类型优先，不用标签凑正文长度。

## 构建

```powershell
python .agents/skills/videohub-film-commentary/scripts/build_film_commentary_publish_package.py `
  "<film_commentary.mp4>" `
  --plan "<job_dir>/publish_plan.json" `
  --qa-report "<job_dir>/film_commentary_qa.md" `
  --cover-source "<optional_clean_video.mp4>"
```

脚本校验标题、文案、话题、封面字段和 QA 状态，生成竖版封面并验证尺寸、亮度变化和
文件大小。`--cover-source` 可用于从没有顶部解说字幕的中间成片取帧；未提供时使用正式成片。

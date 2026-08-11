# Series Commentary Job 1.0

连续多集影视解说使用两个数据文件，把稳定生产参数与逐集剧情内容分开：

- `data/series_spec.json`：系列名称、素材路径、TTS、音量、画幅、封面和输出目录。
- `data/episode_specs.json`：每集时长、剧情摘要、旁白块、选段起点、封面文案和发布文案。

API Key、Cookie、Token 和密码只能通过本地环境变量或未跟踪的 `.env` 提供，不能写入配置。

## series_spec.json

```json
{
  "schema_version": "1.0",
  "series": {
    "title": "示例剧名",
    "slug": "example_series",
    "source_language": "zh-CN",
    "content_type": "drama"
  },
  "paths": {
    "source_dir": "data/source_episodes",
    "subtitle_dir": "data/subtitles",
    "video_pattern": "episode_{episode:02d}.mp4",
    "subtitle_pattern": "episode_{episode:02d}.srt",
    "episode_specs": "data/episode_specs.json",
    "cover_source": "data/cover_source.png",
    "job_root": "docs/story_jobs",
    "episode_output_root": "outputs/episodes",
    "package_root": "outputs/publish_packages"
  },
  "production": {
    "resolution": [1080, 1920],
    "target_language": "zh-CN",
    "subtitle_mode": "source",
    "burn_subtitles": "none",
    "translation_stage": "post_edit",
    "translation_polish": false,
    "source_audio_stream": 0,
    "duration_tolerance_sec": 0.2,
    "narration": {
      "provider": "minimax",
      "model": "speech-2.8-turbo",
      "voice_id": "Chinese (Mandarin)_Male_Announcer",
      "speed": 1.2,
      "language_boost": "Chinese",
      "max_audio_speedup": 1.25,
      "max_block_tail_gap_sec": 0.75
    },
    "audio": {
      "strategy": "narration_only",
      "original_audio_volume": 0.0,
      "source_audio_volume": 0.0
    }
  },
  "cover": {
    "source": "data/cover_source.png",
    "formats": ["cover_3x4.jpg", "cover_4x3.jpg"],
    "category": "影视解说",
    "focus_x": 0.63,
    "focus_y": 0.48
  },
  "delivery": {
    "hashtags": ["示例剧名", "影视解说", "剧透社"]
  }
}
```

`resolution` 是最终成片 QA 的预期尺寸，不会隐式拉伸源视频。素材画幅与目标不一致时，
应先在故事计划或专用预处理步骤中明确裁切/填充策略。

## episode_specs.json

```json
{
  "1": {
    "duration": 90.0,
    "summary": "本集经过本地字幕、画面和可靠剧情资料核验后的摘要。",
    "angle": "以主人公发现关键秘密为主线。",
    "hooks": ["秘密终于曝光", "他的选择改变结局"],
    "caption": "50 到 100 字的发布文案。",
    "texts": [
      "我是剧透社，今天讲《示例剧名》第1集……",
      "第二个旁白块……"
    ],
    "source_starts": [0.0, 45.0],
    "slot_duration": 45.0,
    "chapter_count": 4
  }
}
```

每个 `texts` 项对应一个连续旁白时间槽。`source_starts` 可省略，执行器会在整集范围内
等距选取画面；正式交付前仍必须人工核对旁白与画面是否同阶段，不能把自动等距选段当作
剧情理解。已验证的项目应显式填写 `source_starts`。

## 执行

```powershell
# 只检查素材、时长、音视频流和选段边界，不调用付费 TTS
python .agents/skills/videohub-film-commentary/scripts/run_series_commentary.py `
  "workspace/projectNNN_series" --episodes 1-12 --stage preflight

# 生成并校验证据、剧情分析、剪辑计划和旁白计划，不调用付费 TTS
python .agents/skills/videohub-film-commentary/scripts/run_series_commentary.py `
  "workspace/projectNNN_series" --episodes 1-12 --stage prepare

# 分阶段恢复，或执行完整生产
python .agents/skills/videohub-film-commentary/scripts/run_series_commentary.py `
  "workspace/projectNNN_series" --episodes 3-5 --stage render
python .agents/skills/videohub-film-commentary/scripts/run_series_commentary.py `
  "workspace/projectNNN_series" --episodes 3-5 --stage all
```

默认复用已有证据、成片、TTS 分块缓存和生产签名一致的发布包。只有明确需要重新构建时
使用 `--force`。旧项目内的 `build_episode_series.py` 保留为历史基线，但新项目不得继续
复制它；差异必须进入配置或通用执行器。

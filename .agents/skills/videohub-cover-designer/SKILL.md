---
name: videohub-cover-designer
description: 为 VideoHub 的影视解说、连续剧、电影、卡点视频和短视频制作可在个人主页小缩略图中辨认的封面。输入剧照、视频帧或已有底图，突出剧名、集数和简短看点，统一生成 9:16、3:4、4:3、16:9 封面与缩略图预览。用于“做封面”“修改封面”“加大集数”“生成横版和竖版封面”“沿用上一集封面模板”“制作抖音或视频号缩略图”等任务。
---

# VideoHub Cover Designer

用实际素材制作缩略图优先的系列化封面。不要只生成文件；必须打开成图检查。

## 工作流

1. 确认剧名、集数、两行以内的封面看点及目标平台。
2. 读取 [cover-design-rules.md](references/cover-design-rules.md)。连续剧先找到上一集封面或配置，继承底图、字体、颜色、人物焦点和版式。
3. 从用户提供的剧照或原视频选择清晰、可辨识的实际画面。避开黑场、模糊帧、源字幕、水印和剧透画面。
4. 使用 `scripts/generate_series_covers.py` 生成目标画幅和清单。只生成用户需要的比例，不要把未要求的画幅塞进发布包。
5. 使用 `view_image` 打开实际请求的封面；人物被裁、文字过小、集数不醒目或文字覆盖脸部时，调整焦点或文案后重跑。
6. 将封面放进当前项目的发布包，保留生成清单。影视解说项目同时核对标题和封面内容确实出现在成片中。

## 生成命令

```powershell
python .agents/skills/videohub-cover-designer/scripts/generate_series_covers.py `
  --source "<剧照或干净视频帧>" `
  --output-dir "<项目目录>/outputs/cover_assets" `
  --title "豺狼的日子" `
  --episode "05" `
  --episode-label "第5集" `
  --hook "骨折靴藏枪" `
  --hook "工厂生死围捕" `
  --category "谍战悬疑 · 影视解说" `
  --focus-x 0.63 `
  --focus-y 0.48 `
  --landscape-focus-x 0.63 `
  --landscape-focus-y 0.20
```

`--focus-x/y` 用于竖版和默认画幅；当竖图生成16:9时人物被裁，可用
`--landscape-focus-x/y` 单独调整横版焦点，不影响已经确认的竖版封面。
横版需要独立构图时，用 `--landscape-source` 传入单独处理的人物右置或左置底图。
用 `--formats cover_3x4.jpg cover_4x3.jpg` 限制输出比例；不需要主页预览时增加
`--no-thumbnail-preview`。

输出：

- `cover_9x16.jpg`：1080x1920
- `cover_3x4.jpg`：1080x1440
- `cover_4x3.jpg`：1440x1080
- `cover_16x9.jpg`：1920x1080
- `thumbnail_preview.jpg`：模拟个人主页小图
- `cover_manifest.json`：输入、参数、尺寸和 SHA-256

`--episode` 可省略，适用于电影或单条视频。`--hook` 最多传两次。人物偏左或偏右时调整 `--focus-x`；人物偏上或偏下时调整 `--focus-y`，取值范围均为 0 到 1。

## 完成标准

- 用户要求的全部图片尺寸正确，文件可解码；未要求的比例不进入发布包。
- 3:4 缩小到约 220 像素宽后，剧名和集数仍可直接辨认。
- 集数使用独立高对比徽标，不依赖小号副标题。
- 人脸、眼睛、武器或关键动作不被文字遮挡，也不被画幅边缘切坏。
- 同一系列各集只改变集数和本集看点，版式、色彩和字体保持一致。
- 不能使用成片未讲到的剧情作标题，也不能用与演员或场景不一致的 AI 剧照。

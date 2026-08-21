# VideoHub 开发日志

本文档用于记录 VideoHub 的重要开发变更。每次向 GitHub 提交或推送代码前，必须同步更新本文档，说明本次更新内容、设计思路、实现方式、验证结果和遗留问题。

## 提交前记录要求

每次准备提交 GitHub 前，至少补充以下内容：

- 更新日期和分支/提交范围。
- 本次解决的问题或新增能力。
- 设计思路：为什么这样设计，和原有能力如何衔接。
- 实现方式：涉及的主要文件、模块、接口或配置。
- 验证结果：运行过哪些检查、测试或手动验证。
- 遗留问题：尚未解决的限制、依赖或后续计划。

建议提交前执行：

```bash
git status --short
git diff --check
python -m py_compile main.py
```

如果本次改动涉及新增 Python 模块，应把对应文件一起加入 `py_compile` 检查。

## 2026-08-11：连续剧解说配置化生产与 README 更新

### 更新内容

- 为影视解说 Skill 新增统一的连续剧执行器，支持 `preflight`、`prepare`、`render`、
  `package`、`audit` 和 `all` 六个阶段，并可按单集或集数范围运行。
- 把系列级 TTS、音量、画幅、封面与路径参数和逐集剧情、旁白、选段、发布文案分开管理，
  后续项目不再复制项目专用 `build_episode_series.py`。
- 修复系列审计脚本硬编码 `1920x1080` 和封面必须位于发布包根目录的问题；审计现可接收
  目标分辨率、所需封面格式和嵌套 `cover_assets/`。
- 中英文 README 在顶部补充系列批量生产、剧集目录模式、影视封面、音乐卡点剪辑和五轨
  时间线精修等近期能力。
- 中英文 README 新增 Codex / Claude Code 快速安装与自然语言使用入口，提供仓库地址、
  安全配置要求，以及 YouTube、抖音、本地电影和连续剧批量剪辑示例；同时合并顶部重复的
  “最新功能”段落，按安装使用、系列生产、工作原理和时间线精修组织内容。
- 发布前将时间线工作台的启动命令改为仓库相对路径，避免 README 依赖开发机上的
  `F:\work\VideoHub` 绝对目录。

### 设计与实现

- 新增 `series_commentary_common.py` 作为配置、路径、素材探测、集数选择和生产签名公共层；
  `run_series_commentary.py` 只负责稳定、可验证的机械流程，剧情理解和旁白内容仍由逐集配置
  和本地证据决定。
- 新增 `series-job-schema.md`，规定 `series_spec.json` 与 `episode_specs.json` 的边界、
  安全要求、恢复规则和执行命令。旧项目脚本暂不删除，保留为回归基线。
- 将 project078 加入新配置格式并对 13 集真实素材执行无付费 API 的预检，验证视频、字幕、
  流信息、时长和选段边界均可被统一入口读取。
- 新增系列配置与执行器单元测试，并同步旧片段缓存测试所需的 `source_audio_stream` 参数。

### 验证结果

- 系列执行器、剧集目录、MiniMax、故事时间线、影视发布包和豆包客户端核心回归：
  `python -m pytest -q tests` 共 60 项通过；其中新增计划集成测试确认执行器生成的剧情分析、故事计划和旁白计划均通过
  现有严格校验器。
- `frontend` 执行 `npm run build` 通过，TypeScript 检查和 Vite 生产构建均成功。
- project078 第 1-13 集 `--stage preflight`：全部通过，未调用 MiniMax、未重新渲染成片。
- 网页后端测试在设置 `PYTHONPATH=website/backend` 后 8 项通过。直接从仓库根目录运行
  `pytest -q` 仍会在收集网页后端测试时因其历史绝对导入 `subtitle_service` 失败；这是现有
  测试入口限制，不是本次功能回归失败。
- 三个相关 Skills 的 `quick_validate.py` 校验通过；新增 Python 文件 Ruff 检查和
  `git diff --check` 通过。
- 提交前再次扫描非忽略文件：未发现真实 API Key、口令、媒体、模型、压缩包或可执行文件；
  `.env`、`AGENTS.md`、`workspace/`、`pretrained_models/`、`website/` 和生成目录继续由
  `.gitignore` 排除。

### 遗留问题

- 通用执行器不会把任意源画面隐式拉伸为配置中的分辨率；画幅不一致时仍需在剪辑计划中
  明确裁切或填充策略。
- 旧项目中的三份批量脚本继续保留，待至少两个新项目稳定使用统一执行器后再考虑归档，
  避免一次性删除历史生产依据。

## 2026-08-05：本地剧集目录项目化处理

### 更新内容

- 本地视频“批量处理（目录）”新增默认开启的“剧集项目模式”。
- 原文字幕、Google 初译、DeepSeek 润色字幕统一保存到视频目录下的 `subtitles/`；音频、
  转录稿、摘要和带字幕视频分别保存到同目录的分类子目录。
- 生成只包含相对路径的 `videohub_project.json`，后续故事剪辑和影视解说 Skill 只需接收
  剧集目录，即可按集数找到视频及最佳字幕版本。
- CLI 的 `--video` 支持目录输入；单文件可用 `--series-project` 写入父目录项目。

### 设计与实现

- 新增 `src/series_project.py`，集中负责项目目录创建、自然集数排序、视频与字幕名称归一化、
  字幕版本分类和清单原子更新，避免 GUI 与 Skills 分别维护文件匹配规则。
- 视频与字幕匹配忽略空格、下划线和连字符差异，并识别 `_google`、`_polished` 及语言后缀；
  清单保存相对路径，整个剧集目录移动后仍可使用。
- `process_local_video()` 增加可选 `project_root`，普通单文件流程仍沿用全局 `workspace/`；
  `process_local_videos_batch()` 仅在开关启用时切换到目录内输出，保持兼容。
- 主 GUI、闲时队列和模块化 worker 均透传 `series_project`，中英文 README 与三个相关
  VideoHub Skills 同步更新目录入口和字幕选择优先级。

### 验证结果

- `python -m py_compile src/series_project.py src/youtube_transcriber.py src/gui/workers/worker_thread.py main.py`
- `python -m pytest -q tests/test_series_project.py`：4 项通过。
- `python -m ruff check src/series_project.py tests/test_series_project.py`：通过。
- `git diff --check`：通过。

### 遗留问题

- 当前目录扫描与原有本地批处理一致，只处理项目根目录下的视频，不递归扫描子目录。
- 本次未执行真实 Whisper 长视频转录，以免产生较长运行时间和额外翻译调用；文件落盘与
  清单发现规则已通过隔离测试验证。
- 仓库完整 `tests` 测试结果为 52 通过、1 失败；失败来自当前未提交的 story editor 改动中
  `restore_or_render_segment()` 新增 `source_audio_stream` 必填参数后，旧测试调用尚未同步，
  与本次剧集目录功能无关。

## 2026-07-22：完成影视解说五轨可视化时间线编辑器

### 更新范围

- 分支：`main`（本地功能检查点）
- 后端与渲染：`src/story_timeline_server.py`、`render_story.py`、
  `validate_story_plan.py`
- 前端：`frontend/story-editor.html`、`frontend/src/story-editor.tsx`、
  `frontend/src/story-editor.css` 及最小构建配置
- 测试与文档：`tests/test_story_timeline_server.py`、`tests/test_story_editor_skill.py`、
  中英文 README 和故事剪辑/影视解说 Skill

### 设计与实现

- 新增本地 FastAPI 时间线服务，自动发现 `workspace/projectNNN_*` 下已有解说项目，并把
  `story_plan.json`、`narration_plan.json`、字幕和证据数据转换为片段相对的五轨时间线。
- 第一阶段实现视频预览、五轨显示、切点拖动、片段拆分/删除/重排、撤销/重做、修订保存
  和完整 FFmpeg 重渲染。每次保存写入 `revisions/rev-*`，不改动原始计划和媒体。
- 第二阶段为视频片段增加内容寻址缓存，只重编码变化片段；旁白文本修改后会标记语音过期，
  可以仅调用 MiniMax 重生成当前块。原声窗口和字幕均可拖动、缩放，字幕文本可直接修正。
- 第三阶段增加音量关键帧、视频和音频淡入淡出、交叉转场、多视频源注册与规格归一化，
  以及使用 DeepSeek 的保守局部旁白改写。可选 API 没有密钥时会明确返回错误，不影响基本
  编辑、保存和本地渲染。
- `.gitignore` 继续排除公共网站原型，只放行时间线编辑器所需的最小前端源码和构建配置，
  避免重新上传此前要求保留在本地的网页内容。

### 验证结果

- 前端执行 `npm run build` 通过；真实浏览器中验证了视频画面、五轨布局、切点拖动、拆分、
  删除、重排、撤销、旁白修改、MiniMax 单段生成、原声窗口与字幕调整，以及第三阶段控件。
- 使用真实解说项目完成 5 秒、10 秒和双片段交叉转场渲染；0.5 秒交叉转场成片时长约
  9.57 秒，符合两个 5 秒片段减去重叠时长并计入编码尾差的预期。
- 验证同一片段第二次渲染命中缓存；验证主素材与第二个本地 MP4 可在同一成片中使用。
- DeepSeek 局部改写成功返回并更新选中旁白；MiniMax 返回无效短音频时会拒绝缓存。
- 版本控制范围内的 `tests/` 全量测试为 `44 passed`；Ruff、Python 语法编译、前端生产
  构建和 `git diff --check` 均通过。

### 遗留问题

- 工作台目前是仅供本机使用的精修工具，未加入 PyQt6 主窗口，也不应暴露到公网。
- 浏览器预览能显示片段和交叉转场重叠位置，但最终混合效果以 FFmpeg 渲染结果为准。
- MiniMax 和 DeepSeek 功能依赖用户本地的 API Key、余额和服务可用性。
- 长项目的片段缓存会占用磁盘，后续可在桌面清理工具中增加按项目清理入口。
- 测试环境仍有 `pytest-asyncio` 默认 fixture scope 的第三方弃用警告，不影响本次功能。
- 直接从仓库根目录运行无范围的 `pytest` 会收集本地且被忽略的 `website/backend/tests`，
  该目录依赖自己的模块路径；本次提交使用 `python -m pytest -q tests` 审计版本控制范围。

## 2026-07-22：README 同步影视解说时间线规划与项目目录规范

### 更新范围

- 分支：`main`（本地检查点提交）
- 主要文件：
  - `README.md`
  - `README_en.md`

### 设计与实现

- 在中英文 README 的故事剪辑与影视解说介绍后增加“可视化时间线”规划说明，明确计划
  提供视频、原声、TTS 旁白、原声锚点和字幕的多轨管理，以及人工调整切点后复用未变化
  片段与 TTS 缓存的能力。
- 明确该界面目前尚未实现，不能作为现有桌面 GUI 功能宣传；其定位是 AI 初剪后的人工
  精修入口，最终输出仍交给本地 FFmpeg 确定性渲染。
- 把故事任务的主要目录说明更新为 `workspace/projectNNN_<project_name>/` 独立项目规范，
  同时保留底层脚本对 `review_packs/story_editor`、`videos_with_subtitles` 和
  `publish_packages/douyin` 默认目录的兼容说明。
- 英文 README 版本号同步为 `v0.3.0`，与中文 README 保持一致。

### 验证结果与遗留问题

- `git diff --check -- README.md README_en.md` 通过。
- 已确认中英文均明确使用 planned/规划中表述，没有把尚未实现的网页时间线写成现有功能。
- 时间线工作台仍处于方案阶段；后续实现前需要先升级旁白和原声窗口的片段相对锚点，
  并为 FFmpeg 渲染器增加片段级缓存，避免调整单个切点后重做全部视频。

## 2026-07-20：中英文 README 同步故事剪辑与影视解说 Skills

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 主要文件：
  - `README.md`
  - `README_en.md`

### 设计与实现

- 在中英文 README 顶部新增“故事剪辑与影视解说 Skills”更新区，用统一流程图说明
  “视频和字幕 -> 证据提取 -> 故事理解 -> 剪辑规划 -> 剪辑后翻译/TTS -> 确定性渲染
  -> 成片与发布包”的工作方式。
- 分别说明 `videohub-story-editor` 和 `videohub-film-commentary` 的适用内容、音频策略、
  字幕方式和交付物。故事剪辑支持原声双语版与 MiniMax/豆包 TTS 版；影视解说使用
  第三者旁白并保留不与旁白重叠的关键角色原声。
- 明确外文素材先基于原文字幕和画面证据理解、选段，之后才按最终时间轴重新翻译，避免
  把剪辑前逐句机翻当成剧情判断依据；最终译文可选用 DeepSeek 做轻度整体润色。
- 增加可直接交给智能助手的中英文请求示例，以及 `review_packs/story_editor`、
  `videos_with_subtitles`、`publish_packages/douyin` 的产物说明。
- 在 Skills 表格、核心功能/Feature Overview、项目目录和英文典型场景中同步两项能力；
  英文 README 版本号由过期的 `v0.1.1` 对齐到中文 README 的 `v0.2.4`。
- 明确这些能力当前是项目级智能助手工作流，会编排仓库中的 Python/FFmpeg 脚本，并非
  PyQt6 桌面界面中的一键剪辑按钮，避免对最终用户造成错误预期。

### 验证结果与遗留问题

- 中英文 README 均包含两个 Skill 的功能定位、流程、调用示例、产物目录和权利边界。
- 已检查两份文档的 Mermaid 代码块、Markdown 表格、相对链接和目录树结构；中英文功能
  描述保持一致，英文版本号已同步。
- 本次仅更新文档，没有重新执行媒体渲染；两个 Skill 的脚本与真实样片验证记录见本日志
  同日更早条目。
- 故事剪辑和影视解说目前仍依赖支持项目级 Skills 的智能助手进行分析与计划，未来如加入
  GUI 一键入口，需要再次更新 README 的使用说明和能力边界。

## 2026-07-20：增加 MiniMax 中文音色批量试听与缓存对比页

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 主要文件：
  - `.agents/skills/videohub-film-commentary/SKILL.md`
  - `.agents/skills/videohub-film-commentary/scripts/generate_minimax_voice_samples.py`
  - `main.py`
- 本地试听产物：
  `workspace/dubbing_temp/voice_previews/minimax_comparison/speech-2_8-turbo/afb935f11c16/`

### 设计与实现

- 使用同一段包含人物、冲突、转折和停顿的影视解说文案，批量比较 12 个普通话系统音色，
  覆盖播报、电台、温润、沉稳、抒情、生活化男声，以及新闻、成熟、御姐、温暖和甜美女声。
- 输出独立 WAV、`manifest.json` 和可直接在浏览器打开的 `index.html`。页面并列展示音色名、
  原生播放控件、适用场景、Voice ID 和实际时长，避免来回进入设置逐个生成和试听。
- 缓存路径同时包含模型和测试文本 SHA-1。再次运行会验证 WAV 后直接复用；只有文件缺失、
  损坏或显式传入 `--force` 时才调用 MiniMax，减少等待、限流和重复费用。
- 单个音色生成失败不会终止整批任务，失败原因会进入页面和 manifest；客户端仍复用项目
  现有的请求节流、HTTP 重试和 MiniMax `status_code=1002` 退避逻辑。
- 设置中的 MiniMax 音色列表补充本次已实际调用成功的抒情男声、真诚青年、阅历姐姐、
  温暖闺蜜、御姐、成熟女性和甜美女性，试听后可直接选择对应音色。

### 验证结果与遗留问题

- `speech-2.8-turbo` 下 12/12 个音色真实生成成功，均为 32000 Hz、单声道有效 WAV，时长
  12.79-18.68 秒；试听页包含 12 个音频源且全部存在。
- 第二次运行 12/12 个音色全部命中缓存，没有再次调用语音合成接口。
- `py_compile` 已通过批量脚本和 `main.py`；CLI `--help` 正常。
- 短样片适合排除明显不合适的音色，但无法代替长旁白试听。正式影视解说仍应再生成
  30-60 秒真实文案，检查长句停顿、情绪持续性、专有名词和听觉疲劳。

## 2026-07-20：影视解说 Skill 增加抖音封面、标题和完整发布物料

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 主要文件：
  - `.agents/skills/videohub-film-commentary/SKILL.md`
  - `.agents/skills/videohub-film-commentary/agents/openai.yaml`
  - `.agents/skills/videohub-film-commentary/references/douyin-publish-plan-schema.md`
  - `.agents/skills/videohub-film-commentary/scripts/build_film_commentary_publish_package.py`
  - `.agents/skills/videohub-story-editor/scripts/build_douyin_publish_package.py`
  - `.agents/skills/videohub/SKILL.md`
  - `tests/test_film_commentary_publish.py`
  - `requirements.txt`

### 设计与实现

- 将抖音发布物料从“用户额外要求时可选生成”改为影视解说成片后的默认交付；用户明确
  不需要时才省略。发布包包含正式视频、1080x1920 竖版封面、3-5 个标题候选、已选标题、
  50-100 字中文文案、3-8 个话题、发布说明、发布计划和媒体清单。
- 新增 `publish_plan.json` schema。标题候选必须分别填写角度和剧情证据引用，已选标题必须
  与一个候选完全一致，从输入层阻止无证据的金额、身份、结局或夸张说法进入发布物料。
- 封面使用成片或无顶部解说字幕的中间视频真实取帧，不生成与演员、服装或场景不一致的
  AI 剧照。脚本使用 Pillow 把横版画面按人物焦点裁成 1080x1920，提供顶部/底部两种文字
  区域，并按像素宽度动态调整中英文混排字号和换行。
- 封面设计使用白色主标题、黄色副标题、红色短分隔线和半透明深色文字区；主要文字放在
  抖音中部安全区，标题与人物表情分区。脚本验证 JPEG 尺寸、文件大小和亮度标准差，仍要求
  执行者实际打开封面检查人物裁切和文字位置。
- 构建器复用故事剪辑发布包的 H.264/AAC 探测、硬链接/复制、SHA-256、文案校验和 FFmpeg
  取帧。通用 QA 检查同时接受英文 `Result: PASS` 和中文 `结果：PASS` 标记。
- `requirements.txt` 增加 Pillow 依赖；影视解说 Skill 的触发描述、默认提示和 VideoHub
  总入口路由同步加入封面、标题、文案与发布物料能力。

### 真实样片验证

- 使用《Lucky》第一集 10 分钟影视解说成片生成完整发布包：
  `workspace/publish_packages/douyin/Lucky_2026_S01E01_10分钟影视解说/`。
- 生成 4 个有事件/主题证据引用的标题候选，选定“丈夫卷走一千万，她被FBI和黑帮同时
  追杀”；文案为 71 个可见字符，话题为 5 个。
- 第一版前向测试发现 `focus_x` 被错误实现为裁剪偏移比例，虽然尺寸检查通过，但女主面部
  被裁出画面。实现已改为真正的“人物焦点坐标”，并新增左右主体焦点单元测试。
- 第二版封面人物居中，但底部文字区压住眼睛；根据该帧上方留白切换顶部布局并缩短文字区，
  最终封面完整保留双眼和表情，标题、人物和剧集标签均清晰可读。

### 验证结果与遗留问题

- 新旧发布流程测试共 18 项通过，覆盖计划字段、候选标题、中文 QA、文案/话题、人物焦点
  裁剪和实际 1080x1920 JPEG 输出。
- 真实发布包视频通过 H.264/AAC 媒体探测，封面、标题、文案、话题、说明和 manifest 均已
  生成；符合条件时使用硬链接，避免再次复制 300 MB 以上成片。
- 自动 QA 只能发现空白、尺寸、字段和编码问题，不能可靠判断是否遮挡眼睛、人物是否选错
  或标题是否最有传播力；Skill 因此把人工打开封面和抽查发布视频设为强制步骤。
- 横版成片仍保持原比例，当前只生成竖版封面。需要真正的 9:16 视频时，必须单独设计重构
  画面并重新 QA，不能直接使用封面裁图逻辑强裁整条视频。

## 2026-07-20：完成《Lucky》第一集 10 分钟混合影视解说样片

### 更新范围

- 分支：`main`（本次仅生成本地样片和验证记录，未提交、未推送）
- 源视频：47 分 30 秒、1918x802 的英文犯罪剧情片，画面已烧录中英字幕，没有独立字幕流。
- 正式成片：
  `workspace/videos_with_subtitles/Lucky_2026_S01E01_10min_film_commentary.mp4`
- 分析与 QA：
  `workspace/review_packs/story_editor/lucky_2026_s01e01_10min_film_commentary/`

### 设计与实现

- 使用 `videohub-film-commentary` 的五层流程完成真实长视频验证：先建立字幕、镜头、关键帧
  证据包，再分析人物、事件和因果，最后由确定性脚本执行剪辑、混音和字幕烧录。
- Whisper small 生成 703 个转写片段，但歌曲和无对白段出现重复歌词幻觉。正式证据改用与
  片源硬字幕对齐的 380 条英文字幕，并据此建立 413 个镜头、80 张关键帧和 10 个分析块。
- 从整集选取 23 个片段组成严格 600 秒时间线。解说采用 32 个第三者旁白块，并保留 8 个
  冲突、承诺和生存告诫原声锚点，共约 69.7 秒，占成片约 11.6%。旁白区原片声为 30%，
  进入原声窗口后恢复到 100%。
- 最终剪辑后重新生成 123 条对白字幕。Google 翻译遇到 HTTP 429 后自动回退 DeepSeek，
  再做整体润色和少量人工语境校正，同时保留原文、初译和润色版用于对比。
- MiniMax `speech-2.8-turbo` 的中文男声一次生成 32 个旁白片段；重建精简屏幕字幕时全部
  命中本地缓存。两段因时长适配发生轻微加速，最高约 1.06 倍。
- 片源底部已有中英硬字幕，因此没有重复烧录对白字幕。新增解说字幕采用顶部两行布局，
  原声窗口不显示顶部文字，避免字幕区域重叠并保留演员台词。

### 验证结果

- `story_analysis.json`、`story_plan.json` 和影视解说 `narration_plan.json` 均通过校验，
  旁白计划为 0 个错误、0 个警告。
- 正式成片时长 600.016 秒，H.264/AAC，1918x802，48 kHz 双声道，约 308.45 MiB；
  FFmpeg 完整解码无错误。
- 在 13 个时间点抽查旁白、原声、追逐、审问、翻车和结尾画面。顶部字幕出现/消失符合
  计划，底部中英硬字幕保持可读，没有乱码、越界或同区域覆盖。
- SHA-256：`1413F97E3BF9D09A281147A7FB73E62E8C5B7DB94FE1465EEFE4021B23DF25BC`。
- 独立 QA 报告：
  `workspace/review_packs/story_editor/lucky_2026_s01e01_10min_film_commentary/final_commentary_qa.md`。

### 遗留问题

- 片源自带的对白或歌词硬字幕无法无损去除，因此旁白区偶尔会同时看到顶部解说和底部
  原片文字；当前通过上下分区降低干扰。
- 与片源匹配的外部英文字幕仍属于参考输入。关键人物、金额、追捕关系和动作结果已结合
  画面、原声及多处字幕证据复核，但正式发布前仍应由人工观看整条成片。
- 本次保留 1918x802 宽银幕比例，没有为了名义上的 1080p 拉伸或加黑边。
- 素材发布、转载和平台传播仍需使用者确认版权、合理使用和平台规则。

## 2026-07-20：新增影视剧第三者旁白与关键原声混合解说 Skill

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 分析样本：
  - 《东京出租车》影视解说文案及对应抖音视频。
  - 《独身女性》影视解说文案及对应抖音视频。
- 主要文件：
  - `.agents/skills/videohub-film-commentary/`
  - `.agents/skills/videohub-story-editor/SKILL.md`
  - `.agents/skills/videohub-story-editor/references/narration-plan-schema.md`
  - `.agents/skills/videohub-story-editor/scripts/validate_narration_plan.py`
  - `.agents/skills/videohub-story-editor/scripts/synthesize_story_narration.py`
  - `.agents/skills/videohub-story-editor/scripts/render_story.py`
  - `.agents/skills/videohub/SKILL.md`
  - `tests/test_story_editor_skill.py`

### 样本分析结论

- 两份现成解说文案都是无时间码的一行式 ASR 文本，存在错字、重复和说话人混杂，不能仅靠
  文本可靠判断哪些句子来自解说、哪些来自演员原声。因此使用 Whisper small 对对应视频重新
  建立时间轴，共得到 975 和 612 个语音片段，并结合短窗口语言检测及候选画面人工复核。
- 样本中的原声候选约占片长 4.2% 和 6.3%。这些片段集中在人物决定、关系揭露、冲突反问、
  笑点、承诺、和解和告别，而人物背景、时间跨度、行动过程、支线和因果连接主要由第三者
  旁白承担。
- 影视解说默认以第三者旁白压缩剧情，只在“声音和表演本身比信息摘要更重要”时恢复影视
  原声。原声前先提供最低限度背景，原声后保留短暂停顿、表情或环境声，不能用旁白抢答角色。

### 设计与实现

- 新增 `videohub-film-commentary`，复用故事剪辑 Skill 的证据提取、故事理解、剪辑、后置
  翻译、TTS、字幕和发布包流程，只增加影视剧专用的旁白/原声切换策略。
- 混合解说计划增加 `audio_strategy=hybrid_source_anchors`、
  `source_audio_windows`、`original_audio_volume` 和 `source_audio_volume`。旁白块和原声窗口
  都基于最终成片时间轴并引用字幕、事件、画面或剪辑片段证据。
- 默认建议原声占成片 5%-12%，单个锚点 2-10 秒、每条约 4-8 个；这只是起始参数，不作为
  所有题材的固定比例。校验器会拒绝原声与旁白重叠、越界、缺少证据和超过 30 秒的原声段，
  并对异常比例或过长片段给出警告。
- 渲染器在旁白区把原片声音保持为 30%，进入原声锚点后恢复为 100%；原声窗口对应的最终
  原文/译文字幕会与 TTS 旁白字幕合并，外语对白可继续输出中文或双语字幕。
- 总入口已增加影视解说路由；普通故事重排仍使用 `videohub-story-editor`，影视剧第三者解说
  与关键原声混剪使用 `videohub-film-commentary`。

### 验证结果

- 新旧两个 Skill 均通过 `quick_validate.py`，新增和修改的 Python 脚本通过 `py_compile`
  与 Ruff 检查。
- 独立影视解说计划校验器完成正反验证：合法混合计划通过；原声窗口和旁白重叠时返回失败。
- 故事剪辑目标测试共 13 项通过，覆盖原声计划校验、重叠拒绝、字幕裁剪合并和动态音量表达式。
- 使用 4 秒合成素材完成 FFmpeg 动态混音冒烟测试：原声窗口内外 RMS 比值为 3.337，符合
  0.30 到 1.00 的音量恢复设计，输出完整解码无错误。

### 分析产物与遗留问题

- 样本转写、语言窗口、候选帧和联系表保存在
  `workspace/review_packs/film_commentary_samples/`，仅作为本地设计依据，不属于 Skill 运行依赖。
- 短窗口语言检测只能辅助定位演员原声，可能把歌曲、环境声、短语或多人叠音误判；正式任务
  仍需结合原文字幕、画面、声音和剧情功能复核。
- 5%-12% 是从当前两个样本和影视解说节奏推导出的默认范围，不是平台规范。悬疑、喜剧、
  动作、家庭剧等题材应根据对白价值和表演密度调整。
- Skill 不替代素材授权、合理使用和平台规则判断，发布前仍需用户确认版权与使用边界。

## 2026-07-20：故事剪辑增加抖音发布包和 50-100 字文案

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 主要文件：
  - `.agents/skills/videohub-story-editor/SKILL.md`
  - `.agents/skills/videohub-story-editor/scripts/build_douyin_publish_package.py`
  - `.agents/skills/videohub-story-editor/agents/openai.yaml`
  - `.agents/skills/videohub/SKILL.md`
  - `src/paths_config.py`
  - `tests/test_story_editor_skill.py`

### 本次更新内容

- 故事成片 QA 通过后，可生成独立抖音发布文件夹，统一放在
  `workspace/publish_packages/douyin/<package_name>/`。
- 发布包包含 H.264/AAC MP4、`caption.txt`、`hashtags.txt`、`cover.jpg`、
  `publish_notes.md` 和 `publish_manifest.json`。
- 中文正文强制为 50-100 个可见字符，空白不计入长度；正文必须包含中文，话题标签
  独立保存，不能依靠标签凑长度。
- 清单记录媒体参数、文案长度、来源链接、QA 报告、传输方式和视频 SHA-256，便于
  发布前复核与追溯。

### 设计与实现

- 已是 MP4/H.264/AAC 的成片优先创建 NTFS 硬链接，发布文件夹可直接使用，同时不重复
  占用一份大视频空间；硬链接失败时回退为复制。
- 输入编码不符合要求或显式使用 `--transcode` 时，通过 FFmpeg 转为 H.264/AAC MP4，
  并设置 `faststart`。
- 可通过 `--cover-time` 从最终成片抽取代表画面；封面时间必须位于成片范围内。
- 传入 QA 报告时必须识别到 `PASS` 才能继续打包；打包后再次使用 FFprobe 检查视频、
  音频和时长。
- 横版成片默认保持原构图和 1080P，不自动裁成 9:16，避免人物、字幕和关键物体被裁掉。

### 真实样片验证

- 使用 `03lvf9P3znw` 的 4 分钟 MiniMax TTS 成片生成发布包：
  `workspace/publish_packages/douyin/2026款丰田RAV4混动通勤实测_油耗与舒适性表现如何/`。
- 正文为 73 个可见字符，话题为 `#丰田RAV4 #混动SUV #汽车评测 #通勤实测`。
- 发布视频为 1920x1080、60000/1001 fps、H.264/AAC、48 kHz 双声道，时长
  240.659 秒；完整 FFmpeg 解码无错误。
- 发布视频通过硬链接复用成片，SHA-256 为
  `de9d8f2f2cd2e10934f0be0d37680e352810c6f23ae2ca9a925f9374b4529cfd`。
- 5 秒位置的封面候选已人工检查，车辆主体和烧录字幕均清晰、未越界。

### 遗留问题

- 9:16 竖版需要根据具体画面重新排版并单独 QA，本次仅生成保留原构图的 1080P 横版发布包。
- 平台规则、版权授权、最终标题和封面仍需发布前人工复核。
- Windows 下运行 Skill 校验器时需要 `PYTHONUTF8=1`，否则校验器可能使用 GBK 读取
  中文 `SKILL.md` 并报 `UnicodeDecodeError`。

## 2026-07-20：完成 RAV4 四分钟 MiniMax TTS 解说样片

### 更新范围

- 分支：`main`（本次未提交、未推送）
- 输入视频：YouTube `03lvf9P3znw`，原片 38 分 35 秒
- 主要文件：
  - `.agents/skills/videohub-story-editor/scripts/synthesize_story_narration.py`
  - `workspace/review_packs/story_editor/03lvf9P3znw_rav4_4min_tts/`
  - `workspace/videos_with_subtitles/2026_Toyota_RAV4_Hybrid_03lvf9P3znw_4min_TTS_minimax.mp4`

### 本次更新内容

- 使用故事剪辑 Skill 完成真实长视频样片：基于英文原生字幕和画面证据理解内容，重排为 20 个片段、总计划时长 240 秒。
- 编写 20 段中文解说，使用 MiniMax `speech-2.8-turbo` 和中文男声 `Chinese (Mandarin)_Male_Announcer` 合成。
- 将原片声音降到 30%，混入完整中文解说轨，并烧录与实际 TTS 时长对齐的中文字幕。
- 独立运行解说合成脚本时自动加载项目根目录 `.env`，避免桌面程序外执行时无法读取 MiniMax Key。

### 设计与实现

- 故事理解、剪辑计划、解说计划和确定性渲染继续分层保存，事实与画面选择均可从 `story_analysis.json`、`story_plan.json` 和来源映射中追溯。
- 20 个片段统一为 12 秒，覆盖车型定位、动力油耗、空间、交互、城市与高速体验、缺点和结论；其中 30% 为视觉主导片段。
- 每段解说单独生成并缓存，再按输出时间轴归一化和拼接；实际最大语速调整约 1.12 倍，低于 1.25 倍上限。
- MiniMax `Chinese (Mandarin)_Radio_Host` 在当前账户请求中长时间无响应，最小请求验证后改用可正常生成的 `Male_Announcer`，保留男声解说方向。

### 验证结果

- `story_analysis.json`、`story_plan.json`、`narration_plan.json` 均通过校验，0 个警告。
- 20 段 TTS 全部生成成功，合成音轨为 240.000 秒，字幕共 20 条。
- 成片为 H.264/AAC、1920x1080、60000/1001 fps、48 kHz 双声道，实际时长 240.659 秒，大小约 230.5 MiB。
- 完整 FFmpeg 解码无错误，QA 报告结果为 `PASS`；抽检 5 秒、120 秒和 232 秒画面，画面有效，字幕清晰且未越界。

### 遗留问题

- `Radio_Host` 音色在有效密钥下可能长时间不返回，后续应给单段 TTS 增加可配置的硬超时、音色预检和明确回退提示。
- 当前字幕按解说块显示，块间保留约 1.8 秒视觉与听觉停顿；更细粒度的逐句字幕可在后续版本中增加。
- 本次为单个汽车评测样片，叙事节奏和 30% 背景音比例仍需在剧情、播客等类型上继续验证。

## 2026-07-20：故事剪辑增加后置翻译和双版本 TTS 解说流程

### 更新范围

- 分支：`main`
- 主要文件：
  - `.agents/skills/videohub-story-editor/`
  - `src/doubao_tts_client.py`
  - `tests/test_story_editor_skill.py`
  - `tests/test_doubao_tts_client.py`

### 本次更新内容

- 外文视频改为先使用原文字幕理解、选段和重排，再对最终成片时间轴重新翻译。
- 最终字幕可以继续使用 Google 基础翻译，并可选 DeepSeek 全局轻度润色；没有
  DeepSeek Key 时保留基础翻译，不影响剪辑和原声版。
- 原声版保留原片声音，可烧录原文、译文或双语字幕。
- 新增 TTS 解说版：复用同一剪辑计划，把原声音量降到 30%，混入 MiniMax 或豆包
  中文旁白，并烧录跟随实际语音时长的中文字幕。
- 解说文案使用独立 `narration_plan.json`，每个叙述块必须引用真实事件、字幕、画面
  或剪辑片段证据。
- 分段 TTS 结果按供应商、音色、语速和文本缓存；文案未变化时不重复请求。

### 设计思路

剪辑前的逐句机翻缺少最终叙事顺序的上下文，重排后也容易出现术语、指代和语气不
连贯。因此故事理解以原文证据为准，剪辑计划确定后先重建最终原文 SRT，再翻译这份
字幕。DeepSeek 润色只作为可选增强层，不能成为原声版的硬依赖。

原声版和解说版使用同一 `story_plan.json`，保证两种输出的画面来源、先后顺序和
证据链一致。解说版不把 TTS 文案塞回原片字幕，而是单独校验和合成完整旁白轨，最后
由 FFmpeg 将原声按 0.30 音量混入。这样 MiniMax、豆包或凭据故障只影响解说版，
不会破坏已经完成的故事分析、后置翻译和原声成片。

### 实现方式

- `compile_story_plan.py` / `validate_story_plan.py`
  - 增加 `translation_stage` 和 `translation_polish`。
  - `post_edit` 模式允许证据包没有预翻译文本，但要求渲染双语版前注入完整译文。
- `prepare_story_subtitles.py`
  - 按最终选段、重排和播放速度重建原文 SRT。
- `translate_story_subtitles.py`
  - 复用现有字幕翻译和 DeepSeek 润色流程，并生成实际执行状态清单。
- `render_story.py`
  - 支持外部后置译文、变体独立字幕前缀和 QA 路径。
  - 支持将对齐的旁白轨与 30% 原声混合，统一到 48 kHz 并限幅后再烧录解说字幕。
- `validate_narration_plan.py` / `narration-plan-schema.md`
  - 校验解说风格、证据引用、时间范围、重叠、文字密度、供应商和音色配置。
- `synthesize_story_narration.py`
  - 支持 MiniMax 和豆包，按块缓存、测量真实时长、有限加速、对齐完整音轨和字幕。
- `src/doubao_tts_client.py`
  - 封装豆包异步长文本 TTS 的提交、查询、WAV 下载和任务恢复。
  - Access Token 不写入任务清单或缓存文件。

### 验证结果

已执行：

```bash
python -m py_compile <全部故事剪辑脚本> src\doubao_tts_client.py
python -m pytest tests -q
python -m ruff check .agents\skills\videohub-story-editor\scripts src\doubao_tts_client.py tests\test_story_editor_skill.py tests\test_doubao_tts_client.py
```

- 项目根 `tests/` 测试：`19 passed`。
- Skill 结构校验：`Skill is valid!`。
- FFmpeg 3 秒合成媒体冒烟验证通过：原片 H.264/AAC 与旁白 WAV 混合后仍为
  H.264/AAC、48 kHz，输出时长为 3.018 秒。
- 未调用真实 MiniMax 或豆包接口，避免在没有用户确认的情况下消耗配额；HTTP 协议
  通过模拟提交、查询和下载响应测试。

### 遗留问题和后续计划

- 当前能力先作为 Skill 和命令行流程提供，尚未接入 VideoHub 桌面 GUI 的故事剪辑页。
- 豆包音色 `voice_type` 需要使用账户已开通的音色；不同账户可用列表可能不同。
- 解说版当前使用固定原声音量，尚未按对白区间自动闪避或动态压低背景声。
- 解说文案仍由执行 Skill 的模型生成，正式发布前应人工检查事实、版权和叙事语气。
- 从仓库根执行不限定目录的 `pytest -q` 时，现有网页版测试
  `website/backend/tests/test_subtitle_service.py` 因直接导入 `subtitle_service` 而在
  收集阶段失败；本次未修改该独立测试入口。

## 2026-07-20：实现基于证据的长视频故事剪辑 Skill

### 更新范围

- 分支：`main`
- 主要文件：
  - `.agents/skills/videohub-story-editor/`
  - `.agents/skills/videohub/SKILL.md`
  - `tests/test_story_editor_skill.py`

### 本次更新内容

本次把原来的故事剪辑规则扩展为可执行的四层流水线：

```text
视频和字幕
  -> 证据提取层
  -> 故事理解层
  -> 剪辑规划层
  -> 确定性渲染层
  -> 短视频和同步字幕
```

新增能力包括：

- 从现有 SRT、VTT、ASS/SSA 字幕和源视频生成 `evidence_pack.json`。
- 提取媒体信息、标准化原文与译文字幕、场景边界、字幕空档视觉候选、关键帧和长视频分析分块。
- 定义模型无关的 `story_analysis.json`，供 Codex、Claude Code、DeepSeek 等模型使用同一套证据引用和输出结构。
- 校验内容分类、分块覆盖、人物或说话人、事件、因果关系、视觉发现、连续性约束和故事方案。
- 把模型生成的 `story_plan.draft.json` 编译为正式 `story_plan.json`，由脚本计算输出时间轴、字幕文本、场景引用和输出路径。
- 对剪辑计划执行跨文件校验，检查字幕、场景、分析节点、来源指纹和时间范围。
- 根据计划确定性裁剪和重排原视频，并重建原文 SRT、译文 SRT 和双语 ASS。
- 支持选择不烧录、原文、译文或双语字幕；成片后执行时长、字幕边界和完整解码检查。

### 设计思路

本功能不引入 WhisperX，也不替换 VideoHub 现有 Whisper、平台字幕、翻译、配音和
GUI 流程。缺少字幕时仍调用项目已有的字幕生成能力；故事剪辑 Skill 只消费带时间码
字幕和视频。

大模型负责理解完整内容、提出叙事方案和选择原片范围，但不负责计算输出时间码或
拼写 FFmpeg 命令。所有模型判断都必须引用 `sub-*`、`scene-*`、`frame-*`、
`visual-*` 或 `chunk-*` 证据；时间轴编译、来源检查、渲染、字幕换算和 QA 由
确定性脚本完成。这样可以替换分析模型，同时保持剪辑结果可追溯和可复核。

### 实现方式

- `build_evidence_pack.py`
  - 读取视频和 SRT/VTT/ASS/SSA。
  - 使用 FFprobe 获取媒体参数。
  - 使用 FFmpeg 场景检测和关键帧抽取。
  - 生成标准化字幕、视觉候选和约 300 秒一个的分析分块。
- `validate_story_analysis.py`
  - 校验模型输出是否覆盖全部分块并引用真实证据。
  - 检查事件、因果、主题、视觉发现、连续性约束和故事方案。
- `compile_story_plan.py`
  - 根据证据交集补全字幕和场景引用。
  - 计算连续输出时间轴，生成 `story_outline.md` 和
    `story_source_map.csv`。
- `validate_story_plan.py`
  - 增加证据包与故事分析的跨文件校验。
- `render_story.py`
  - 逐段重新编码、按顺序拼接、重建字幕时间轴、可选烧录字幕并生成
    `qa_report.md`。
- `story_pipeline_common.py`
  - 提供字幕解析、翻译时间配对、字幕输出、FFmpeg/FFprobe 发现、媒体探测和
    JSON 公共函数。

### 验证结果

- 新增脚本通过 `py_compile`。
- `ruff check` 通过。
- Skill 结构校验通过：`Skill is valid!`。
- `tests/test_story_editor_skill.py`：`3 passed`。
- 全部项目测试：`15 passed`。
- 使用 12 秒 H.264/AAC 合成视频完成端到端验证：
  - 识别 4 条字幕、1 个场景、1 个视觉候选、3 张关键帧和 3 个分析分块。
  - 故事分析与剪辑计划校验均为 0 个错误、0 个警告。
  - 将 3 个原片片段重排为计划时长 9.000 秒的双语字幕成片。
  - 实际成片时长 9.120 秒，字幕时间轴检查通过，完整 FFmpeg 解码无错误。

### 遗留问题和后续计划

- 当前 Skill 提供模型无关的数据契约，但未在 VideoHub GUI 中增加 DeepSeek 等
  外部模型的一键调用入口；现阶段由执行 Skill 的 Agent 生成分析文件。
- 确定性 v1 渲染器只执行硬切，`fade` 和 `crossfade` 暂不渲染。
- 未使用说话人分离模型；只有字幕自身包含说话人标签时才能自动保留姓名。
- 场景检测需要解码源视频，超长视频可先跳过或降低抽帧数量。
- 影视剧情类的无字幕动作、表情和空间关系仍需要多模态模型或人工检查关键帧。

## 2026-07-15：右键智能粘贴支持 Pornhub 链接

### 更新范围

- 分支：`main`
- 主要文件：
  - `main.py`

### 本次更新内容

本次扩展在线视频输入框和批量输入框的右键智能粘贴识别范围，新增对 `pornhub.com` 和 `cn.pornhub.com` 链接的支持。

主要内容包括：

- 单链接输入框右键时，如果剪贴板是 Pornhub 视频链接，会直接清空旧内容并粘贴当前链接。
- 批量链接输入框右键时，会把 Pornhub 链接按普通视频链接处理，支持直接粘贴或追加到新行。
- 在线视频、批量处理和 AI 配音页的输入提示同步加入 Pornhub。
- 将智能粘贴平台关键词抽成 `SMART_PASTE_URL_KEYWORDS`，后续新增平台时只需要维护一处。

### 设计思路

Pornhub 这类站点本身可由 yt-dlp 通用处理链路尝试下载和转写，主要缺口在 GUI 输入层：原来的右键智能粘贴只识别 YouTube、Twitter/X、Bilibili、Instagram、TikTok 等关键词，导致剪贴板中是 Pornhub 链接时不会直接自动粘贴。

这次只扩展输入识别和界面提示，不新建独立下载器，也不改变现有处理流程。这样可以继续复用 yt-dlp 的通用平台能力，避免为单个平台重复实现下载逻辑。

### 实现方式

- `main.py`
  - 新增 `SMART_PASTE_URL_KEYWORDS`。
  - `URLLineEdit.contextMenuEvent()` 使用统一关键词判断单行链接。
  - `URLTextEdit.contextMenuEvent()` 使用统一关键词判断批量链接文本。
  - 更新在线视频、批量处理、AI 配音相关输入提示和错误提示。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py
git diff --check
```

手动验证建议：

- 复制 `https://cn.pornhub.com/...` 链接后，在在线视频输入框右键，确认可以直接自动粘贴。
- 在批量处理输入框中右键，确认可以追加或清空后粘贴 Pornhub 链接。
- 如需实际下载，请确认 yt-dlp 版本和网络环境支持该链接。

### 遗留问题和后续计划

- 当前只是加入智能粘贴和通用 yt-dlp 处理入口，没有针对 Pornhub 增加独立下载状态、目录或专用错误提示。
- 成人站点内容使用前仍需遵守当地法律、平台条款和内容授权边界。

## 2026-07-13：README 增加 MiniMax 多音色配音说明

### 更新范围

- 分支：`main`
- 主要文件：
  - `README.md`

### 本次更新内容

本次将 MiniMax 多音色配音能力同步到 README 靠前位置，方便用户打开项目后第一时间看到最新功能。

主要内容包括：

- 在 README 顶部简介后新增“最新更新：MiniMax 多音色配音”。
- 核心功能中的 AI 配音说明补充 MiniMax API。
- AI 配音章节新增 MiniMax 后端能力说明。
- 增加 MiniMax API 配音使用步骤，包括 API Key、模型、音色选择、自定义 `voice_id`、试听和正式配音流程。

### 设计思路

MiniMax 多音色配音是当前较新的功能，如果只放在开发日志或较深的 AI 配音章节中，用户不容易发现。因此 README 顶部采用“最新更新”短节介绍核心价值，后面的 AI 配音章节再给出具体使用方式。

### 实现方式

- `README.md`
  - 新增靠前的最新更新说明。
  - 更新核心功能列表。
  - 在 AI 配音章节补充 MiniMax 后端和使用步骤。

### 验证结果

已执行：

```bash
git diff --check -- README.md
```

### 遗留问题和后续计划

- 英文 README 暂未同步 MiniMax 多音色说明，后续如需要面向英文用户发布，应同步更新 `README_en.md`。

## 2026-07-10：MiniMax 配音增加多音色选择

### 更新范围

- 分支：`main`
- 主要文件：
  - `main.py`

### 本次更新内容

本次把 MiniMax TTS 从单一 Voice ID 输入改为“下拉选择 + 可手填自定义 ID”的配置方式。

主要内容包括：

- 设置页 MiniMax 音色改为可编辑下拉框。
- 预置一组适合中文视频配音的 MiniMax 系统音色，包括男声、女声、主持、播音、青年、成熟声线和粤语男声。
- AI 配音页在切换到 MiniMax 后，会显示同一组音色列表。
- 试听和正式配音都会使用当前配音页选择的 MiniMax voice_id。
- 仍保留手动输入自定义 voice_id 的能力，方便使用 MiniMax 控制台里的自定义音色或后续新增系统音色。

### 设计思路

MiniMax 官方系统音色不只有女声，也有多种中文男声和主持类声线。原来界面只暴露一个 Voice ID 输入框，使用者很难知道有哪些可选项，也容易一直停留在默认女声。

这次没有把选择做死，而是采用“常用音色下拉 + 可编辑自定义 ID”的方式：普通用户可以直接从列表中选一个男声或女声；熟悉 MiniMax 的用户仍然可以粘贴任意 voice_id。

### 实现方式

- `main.py`
  - 新增 `MINIMAX_VOICE_OPTIONS` 常量，集中维护显示名称和真实 voice_id。
  - 设置页 `MiniMax Voice ID` 输入框改为可编辑 `QComboBox`。
  - 新增 `set_minimax_voice_combo_value()` 和 `get_minimax_voice_id()`，统一处理预置音色、自定义音色和历史 `.env` 配置。
  - `refresh_dubbing_voice_options()` 在 MiniMax 模式下填充完整音色列表。
  - `preview_dubbing_voice()` 和 AI 配音启动参数改为读取当前选中的真实 voice_id。
  - 保存设置时写入真实 `MINIMAX_TTS_VOICE_ID`，不是界面显示名称。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py
git diff --check
```

手动验证建议：

- 在设置页切换到“外部付费 - MiniMax API”，确认 MiniMax 音色下拉框可选择男声和女声。
- 在 AI 配音页确认音色列表跟随 MiniMax 后端切换。
- 选择一个男声试听，确认请求日志中的 `voice_id` 是真实 MiniMax voice_id。
- 手动输入一个自定义 voice_id，保存设置后确认 `.env` 中保存的是该 ID。

### 遗留问题和后续计划

- 当前预置列表只放了常用中文/粤语音色，MiniMax 官方还有更多语言和角色音色，后续可以增加“获取官方音色列表”的接口或导入功能。
- 不同音色的实际效果仍需要通过试听挑选，不能仅按显示名称判断最终风格。

## 2026-07-07：浏览器扩展与字幕翻译流程更新

### 更新范围

- 分支：`main`
- 主要文件：
  - `main.py`
  - `src/youtube_transcriber.py`
  - `src/api_server.py`
  - `src/gui/workers/worker_thread.py`
  - `src/gui/workers/subtitle_thread.py`
  - `src/paths_config.py`
  - `chrome_extension/`
  - `.agents/skills/`

### 本次更新内容

- 字幕翻译增加百分比和时间轴进度输出，长视频或播客翻译时可以看到当前处理到的字幕条数和视频时间。
- Google 翻译触发 429 后会切换到 DeepSeek/OpenAI 备用翻译，并在本轮后续片段跳过 Google，避免反复限流。
- YouTube 浏览器扩展按钮注入逻辑增加重试和新的页面选择器，适配当前页面结构。
- 浏览器扩展增加 TikTok 页面按钮、权限和入队链路。
- 移除一组 legacy platform-specific integration 的 GUI、扩展、API、路径配置和 agent skill 入口，避免继续暴露或执行相关功能。

### 设计思路

长视频翻译的主要问题是用户无法判断等待时间，因此进度以“百分比 + 字幕条数 + 当前视频时间 / 总时长”的方式输出。浏览器扩展侧沿用现有本地队列 API，不新增后端服务；新平台入队复用已有 yt-dlp 下载线程，减少重复实现。

### 实现方式

- `src/youtube_transcriber.py`
  - 增加字幕时间解析、翻译进度输出、DeepSeek/OpenAI fallback 状态日志。
  - 在 SRT 翻译、Whisper 逐段字幕翻译和 DeepSeek 润色阶段输出进度。
- `src/gui/workers/subtitle_thread.py` 与 `main.py`
  - 将字幕翻译核心函数的进度回调接到现有 GUI 进度条和日志框。
- `chrome_extension/`
  - 更新 YouTube content script 的重试注入逻辑。
  - 新增 TikTok content script，并在 manifest、background、popup 中接入。
  - 移除 legacy platform-specific content script、权限、平台分支和展示样式。
- `src/api_server.py`、`src/gui/workers/worker_thread.py`、`src/paths_config.py`
  - 同步清理已移除平台的 API、worker 和输出目录映射。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\api_server.py src\paths_config.py src\gui\workers\worker_thread.py src\youtube_transcriber.py src\gui\workers\subtitle_thread.py
node --check chrome_extension\background.js
node --check chrome_extension\popup\popup.js
node --check chrome_extension\content-scripts\youtube.js
node --check chrome_extension\content-scripts\tiktok.js
python -m json.tool chrome_extension\manifest.json
npm run build
git diff --check
```

并额外执行了全仓关键词残留检查，排除 `.git` 和 `frontend/node_modules` 后无残留。

### 遗留问题

- TikTok 页面结构可能随站点版本变化，后续如按钮位置变化，需要继续按页面 DOM 更新选择器。
- 本地忽略目录中的前端原型已同步清理并重新构建，但该目录当前仍按仓库规则忽略，不随普通提交进入 Git。

## 2026-06-23：本地视频增加歌曲音频提取

### 更新范围

- 分支：`main`
- 主要文件：
  - `main.py`
  - `src/youtube_transcriber.py`
  - `src/gui/workers/worker_thread.py`
  - `src/paths_config.py`

### 本次更新内容

本次在“本地视频”功能中增加独立的音频提取能力，用于把下载好的歌曲视频、MV 或本地视频批量转成音频文件。

主要内容包括：

- 本地视频页新增“音频提取”区域。
- 支持单个视频文件提取音频。
- 支持目录模式扫描并提取目录中的所有视频音频。
- 音频统一输出到 `workspace/songs/`，方便和 YouTube 音频、临时下载音频区分。
- 提取完成后直接提示是否打开歌曲目录。
- `songs/` 加入统一目录映射和清理工具，但默认不清理，避免误删用户整理好的歌曲音频。

### 设计思路

这个功能不复用原来的“转录/总结”按钮，因为用户提取歌曲音频时通常不需要 Whisper 转写、字幕生成或文章总结。单独提供“提取音频到歌曲目录”按钮，可以让本地视频页同时保留知识处理能力和轻量音频整理能力。

输出目录选择 `workspace/songs/`，而不是继续写入 `workspace/youtube_audio/` 或通用下载目录，原因是歌曲音频属于用户后续可能长期保留和整理的文件，应该从目录上就能看出用途。

### 实现方式

- `src/paths_config.py`
  - 新增 `SONGS_DIR` 和 `LOCAL_SONGS_DIR`。
  - 在 `DIRECTORY_MAP` 中注册 `songs` 和 `local_songs`。

- `src/youtube_transcriber.py`
  - 新增 `extract_audio_from_local_videos()`。
  - 复用现有 `extract_audio_from_video()` 和 FFmpeg 提取逻辑。
  - 目录模式按视频相对路径生成音频文件名，减少不同子目录同名视频互相覆盖的问题。

- `main.py`
  - 本地视频页新增“提取音频到歌曲目录”和“打开歌曲目录”按钮。
  - 新增 `extract_local_video_audio()`，把单文件或目录提取任务交给后台线程执行。
  - 完成回调识别目录结果，提示打开输出目录。
  - 清理工具增加 `songs/` 入口，默认不勾选。

- `src/gui/workers/worker_thread.py`
  - 为拆分后的 WorkerThread 同步增加 `extract_audio` 任务类型。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py src/youtube_transcriber.py src/paths_config.py src/gui/workers/worker_thread.py
git diff --check
```

手动验证建议：

- 在“本地视频”页选择单个 MP4/WebM 文件，点击“提取音频到歌曲目录”，确认 `workspace/songs/` 生成 MP3。
- 切换到目录模式，选择包含多个视频的目录，确认可以批量生成音频。
- 提取完成后确认弹窗打开的是 `workspace/songs/` 目录。
- 在清理工具中确认 `songs/` 可扫描，但“常用选择”不默认勾选。

### 遗留问题和后续计划

- 当前音频统一输出 MP3，后续可以增加输出格式选择，例如 MP3、WAV、FLAC。
- 目录模式目前按支持的视频扩展名扫描，后续可以允许用户自定义扩展名或排除子目录。

## 2026-06-18：网页版官网和在线试用工具规划落地

### 更新范围

- 分支：`main`
- 主要文件：
  - `frontend/src/App.tsx`
  - `frontend/src/lib/api.ts`
  - `frontend/index.html`
  - `website/backend/app.py`
  - `website/backend/database.py`
  - `website/backend/download_service.py`
  - `website/README.md`
  - `website/scripts/deploy_vps.sh`

### 本次更新内容

本次恢复历史提交中的网页端代码，并按“项目官网 + 轻量在线试用工具”的定位重新规划。

主要内容包括：

- 首页从单一字幕下载页改为 VideoHub 项目介绍页。
- 第一屏突出 VideoHub 的核心定位：把长视频变成字幕、笔记和可复用知识资料。
- 在线工具区拆成两个 Tab：
  - YouTube 字幕下载
  - 抖音单视频下载尝试
- 桌面版能力区展示下载、转写、字幕翻译、AI 摘要、AI 配音、闲时队列、本地归档等核心能力。
- 增加使用边界说明，明确网页端不是云端 VideoHub。
- 后端新增抖音单视频下载接口。
- 抖音下载支持粘贴完整分享文本，后端自动提取链接。
- 抖音下载结果以临时文件形式保存，返回下载地址、文件名、大小和有效期。
- 后端增加下载临时目录 TTL 清理和容量上限清理。
- 后端增加基础 IP 频率限制，降低在线下载接口被刷的风险。
- 数据库增加 `download_log`，记录抖音下载请求。
- 部署脚本增加 `data/downloads` 目录创建。

### 设计思路

网站不做完整云端版 VideoHub，而是承担两个角色：一个是让用户理解项目的官网，另一个是让用户轻量体验字幕下载和单视频下载。

这样设计的原因是，VideoHub 的核心能力依赖本地环境，包括 FFmpeg、yt-dlp、Whisper、TTS 模型、磁盘目录和用户自己的配置。如果把完整能力搬到服务器，会很快遇到服务器成本、平台限制、版权边界、队列调度和文件清理问题。因此网页端只保留低门槛试用能力，完整工作流继续引导用户去 GitHub 运行桌面版。

抖音下载能力也被刻意限制为“单个公开视频尝试”。不支持主页批量、不支持登录内容、不支持长期保存文件。页面上也明确提示用户只处理自己有权访问和使用的公开内容。

### 实现方式

- `frontend/src/App.tsx`
  - 重构为项目介绍 + 在线工具 + 桌面版能力 + 使用边界。
  - 增加工具 Tab，在字幕下载和抖音下载之间切换。
  - 抖音下载输入框支持完整分享文本。
  - 结果区域显示临时文件有效期和下载按钮。

- `frontend/src/lib/api.ts`
  - 增加 `OnlineDouyinDownloadResult` 类型。
  - 增加 `requestOnlineDouyinDownload()`。

- `website/backend/download_service.py`
  - 新增抖音下载服务。
  - 提取分享文本中的抖音链接。
  - 限制允许的抖音相关域名。
  - 每次下载使用独立 job 目录。
  - 下载完成后写入 `metadata.json`。
  - 清理过期 job，并按总容量删除最旧目录。

- `website/backend/app.py`
  - 增加 `/api/downloads/douyin`。
  - 增加 `/api/downloads/files/<file_id>`。
  - 下载接口增加基础 IP 频率限制。

- `website/backend/database.py`
  - 增加 `download_log` 表。
  - 增加下载请求日志记录方法。

- `website/README.md`
  - 更新网站定位、接口、临时文件清理、环境变量和部署说明。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile website/backend/app.py website/backend/database.py website/backend/download_service.py website/backend/subtitle_service.py
npm run build --prefix frontend
git diff --check
```

手动验证建议：

- 打开首页，确认第一屏是项目介绍，不再只是字幕下载工具。
- 在线字幕下载输入 YouTube 链接，确认可以返回字幕下载链接。
- 抖音下载输入完整分享文本，确认可以提取链接并返回视频下载链接。
- 检查 `/opt/videohub-site/data/downloads` 是否按 job 目录保存文件。
- 缩短 `VIDEOHUB_DOUYIN_TTL_SECONDS` 后确认过期目录能被清理。

### 遗留问题和后续计划

- 抖音下载依赖 yt-dlp 对当前平台规则的支持，可能因平台变化失败。
- 频率限制目前是进程内存级别，重启会清空，后续可改为 SQLite 或 Redis。
- 抖音下载目前是同步请求，大视频或网络慢时前端会等待，后续可改为 job 轮询。
- 视频下载仍有版权和平台条款边界，页面文案和免责声明需要保持明确。
- `frontend/` 和 `website/` 当前仍属于网页端内容，是否上传 GitHub 需要单独确认。

## 2026-06-18：AI 配音自然度优化和字幕烧录选项

### 更新范围

- 分支：`main`
- 主要文件：
  - `src/dubbing_engine.py`
  - `main.py`
  - `src/gui/workers/worker_thread.py`
  - `docs/development_log.md`

### 本次更新内容

本次更新针对 AI 配音正式成片时“试听自然、实际配音偏硬”的问题做优化，并在 AI 配音流程中增加字幕烧录选项。

主要内容包括：

- CosyVoice 正式配音前会对字幕文本做轻度清理。
- 对缺少句末标点的中文字幕自动补句号，帮助 TTS 模型判断停顿。
- 对过短且时间相邻的字幕片段做小范围合并，减少“一条字幕一句话”的机械感。
- CosyVoice Instruct 模式下，如果用户没有填写指令，会自动使用更适合视频讲解的默认指令。
- AI 配音界面新增“字幕烧录”选项：
  - 不压字幕
  - 压单语字幕
  - 压双语字幕
- 配音流程会先生成中文配音视频，再按用户选择烧录字幕。
- 双语字幕使用原字幕和译文字幕生成临时 ASS 文件，再复用现有字幕烧录流程。

### 设计思路

这次没有简单地更换音色，而是从输入结构上改善 TTS 的朗读条件。试听文本通常是一句完整、带标点、带停顿暗示的话，而实际配音来自字幕文件，常常是短句、碎片、缺少标点。如果直接逐条送给模型，模型每次都会重新起句，听起来就容易偏硬。

因此这次优化的重点是：在不大幅改变字幕时间轴的前提下，把字幕片段整理成更适合 TTS 朗读的文本。自动补标点解决的是停顿判断问题，短句合并解决的是语气频繁重启问题，默认 instruct 指令解决的是用户未配置指令时模型风格过于普通的问题。

字幕烧录则放在配音音轨合成之后处理。这样可以保留原有无字幕配音视频，也可以额外得到带字幕版本，流程更清晰，失败时也不会影响基础配音结果。

### 实现方式

- `src/dubbing_engine.py`
  - 增加 `subtitle_burn_mode` 配置。
  - 增加 CosyVoice 字幕片段预处理逻辑。
  - 增加 `_normalize_tts_text()`，用于清理文本和补句末标点。
  - 增加 `_merge_short_segments()`，用于合并过短且时间相邻的字幕片段。
  - 增加 `_burn_selected_subtitles()`，按选项烧录单语或双语字幕。
  - 增加 `_create_bilingual_ass()`，用原字幕和译文字幕生成双语 ASS。

- `main.py`
  - AI 配音页新增“字幕烧录”下拉框。
  - 开始配音时把字幕烧录模式传给后台 Worker。
  - 日志中显示当前字幕烧录选择。

- `src/gui/workers/worker_thread.py`
  - 同步 `subtitle_burn_mode` 参数。
  - 同步字幕烧录步骤日志。

### 验证结果

本次实现后需要执行：

```bash
python -m py_compile main.py src\dubbing_engine.py src\gui\workers\worker_thread.py
git diff --check
```

手动验证建议：

- CosyVoice SFT 模式生成一段配音，确认短字幕不再明显逐字生硬。
- CosyVoice Instruct 模式不填写指令时，确认仍能正常合成。
- 选择“不压字幕”时，只生成普通配音视频。
- 选择“压单语字幕”时，生成带中文字幕的视频。
- 选择“压双语字幕”时，生成带原文和译文两行字幕的视频。

### 遗留问题和后续计划

- 短句合并目前采用保守规则，只合并很短且相邻的字幕，后续可以根据实际样片继续调整阈值。
- 双语字幕目前按字幕顺序配对，如果原字幕和译文字幕段落数量差异较大，可能只能生成部分双语字幕。
- 字幕样式先使用固定 ASS 样式，后续可以接入设置页已有的双语字幕字体和颜色配置。
- 如果用户希望“压字幕后只保留一个最终文件”，后续可以增加输出策略选项。

## 2026-06-17：本地 CosyVoice TTS 配音能力合并

### 更新范围

- 分支：`feature/local-tts-dubbing`
- 合并到：`main`
- 主要提交：
  - `4121109 chore: suppress TensorFlow TTS preview logs`
  - `ff46a36 docs: sync README updates to main`
  - `ab82985 chore: ignore local model and TTS output directories`
  - `b9d76d9 merge: local TTS dubbing feature`

### 本次更新内容

本次更新围绕本地 TTS 配音能力展开，目标是在保留原有默认 TTS 方案的基础上，增加一个可手动切换的 CosyVoice 方案，用于生成质量更好的中文配音。

主要内容包括：

- 新增 `tts_service.py`，使用 FastAPI 封装 CosyVoice 本地服务。
- 支持 CosyVoice SFT、zero-shot、instruct 三类接口。
- 服务启动时加载模型，请求时复用模型，避免每次生成重复加载。
- 长文本按中文标点和换行切分，分段生成后合并为 wav。
- 输出音频保存到 `outputs/` 目录。
- GUI 设置中增加 TTS 后端切换，默认仍使用原有 TTS。
- 选择 CosyVoice 后，配音页音色列表随后端变化。
- 增加音色试听功能，试听文件缓存到 `workspace/dubbing_temp/voice_previews/`。
- 修复试听时 `re` 未导入导致的 `NameError`。
- 抑制 TensorFlow oneDNN 初始化 INFO 日志，减少后台噪声。
- 更新 README，加入 CosyVoice 用法说明和样片链接。
- 新增 `docs/cosyvoice_tts_service.md`，记录 CosyVoice 服务安装、模型目录和运行方式。
- `.gitignore` 增加 `pretrained_models/` 和 `outputs/`，避免提交本地模型和生成音频。

### 设计思路

这次没有把 CosyVoice 模型直接塞进 GUI 主线程，而是拆成独立的本地 FastAPI 服务。这样做主要考虑：

- 模型加载较重，独立服务可以只加载一次，GUI 只通过 HTTP 调用。
- 避免 TTS 模型依赖污染主程序启动流程。
- 后续可以单独重启、替换或优化 TTS 服务，不影响 VideoHub 主界面。
- 保留原有 TTS 作为默认方案，降低新模型不稳定时对用户现有流程的影响。
- GUI 层只暴露“后端选择、服务地址、音色、指令、试听”等必要配置，避免把模型细节暴露给普通使用流程。

音色试听采用缓存策略：相同后端、模式和音色已经生成过试听音频时，后续直接复用旧文件，不再重复调用模型生成。这样可以减少等待时间，也减少本地显存和计算压力。

### 实现方式

主要涉及文件：

- `tts_service.py`
  - FastAPI 服务入口。
  - 提供 `/tts/sft`、`/tts/zero_shot`、`/tts/instruct` 接口。
  - 负责模型加载、文本切分、音频保存和异常处理。

- `src/cosyvoice_tts_client.py`
  - VideoHub 调用 CosyVoice 服务的 HTTP 客户端。
  - GUI 和配音引擎通过它调用本地服务。

- `src/dubbing_engine.py`
  - 扩展 `DubbingTask` 参数，增加 TTS 后端、CosyVoice 地址、模式、音色和指令。
  - 根据后端选择原有 TTS 或 CosyVoice。
  - CosyVoice 模式下按字幕片段生成音频，并按时间戳合并。

- `main.py`
  - 设置页增加 TTS 后端和 CosyVoice 配置。
  - 配音页音色列表根据后端切换。
  - 增加音色试听按钮和试听线程。
  - 增加试听缓存逻辑。
  - 加入 TensorFlow 日志环境变量，减少后台 INFO 输出。

- `src/gui/workers/worker_thread.py`
  - 同步 WorkerThread 参数，让后台任务能收到 TTS 后端和 CosyVoice 配置。

- `README.md`
  - 增加 AI 配音能力说明、样片链接和本地服务启动方式。

- `.gitignore`
  - 忽略 `pretrained_models/`、`outputs/`，避免模型和生成文件进入仓库。

### 验证结果

已执行过的检查：

```bash
python -m py_compile main.py src\dubbing_engine.py src\cosyvoice_tts_client.py src\gui\workers\worker_thread.py tts_service.py
git diff --check
```

手动验证情况：

- CosyVoice 服务可启动。
- SFT 模式生成音质正常。
- GUI 中可以切换 TTS 后端。
- 音色试听可生成并播放。
- 重复试听时可以复用缓存文件。
- TensorFlow oneDNN 提示已通过环境变量压制。

### 遗留问题和后续计划

- CosyVoice 服务需要用户本地提前下载模型，不适合随仓库提交。
- `pretrained_models/` 模型目录体积较大，必须保持忽略。
- zero-shot 音色克隆依赖参考音频路径，后续可以在 GUI 中增加更友好的参考音频选择。
- instruct 模式的指令文本目前较简单，后续可以提供预设模板，例如“自然、稳重、新闻播报、课程讲解”等。
- 当前试听缓存按配置生成文件，后续可以增加清理入口，避免长期积累。
- 不同显卡、CPU 环境下生成速度差异较大，后续需要补充最低配置和推荐配置说明。
- 如果用户没有启动 `tts_service.py` 就切换到 CosyVoice，GUI 需要给出更明确的服务未连接提示。

## 2026-06-21：字幕翻译增加 DeepSeek 可选润色

### 更新内容

- 在设置页增加“Google翻译后使用 DeepSeek 润色中文字幕”开关。
- 默认不开启润色，保持原有翻译流程不变。
- 开启润色后，字幕先按原逻辑完成翻译，再由 DeepSeek 对中文字幕做轻度整体润色。
- 未配置 `DEEPSEEK_API_KEY`、DeepSeek 调用失败或返回格式异常时，自动保留原翻译结果，不影响主流程。
- YouTube、本地音频、本地视频、批量处理、闲时队列、独立字幕翻译和 AI 配音流程都接入同一开关。
- 开启润色时额外保留 Google 初译字幕和 DeepSeek 润色字幕，便于人工查看和对比。

### 设计思路

Google 免费翻译速度快、成本低，但逐句字幕翻译缺少上下文，容易出现术语不统一、中文语序生硬、跨句衔接不自然的问题。直接改成大模型逐句翻译会增加成本和等待时间，也可能破坏字幕条数。

因此本次采用二阶段方案：

```text
原始字幕
  -> Google/当前翻译方式初译
  -> 保存 Google 初译字幕
  -> DeepSeek 轻度润色
  -> 校验条数和 index
  -> 保存 DeepSeek 润色字幕
```

DeepSeek 只处理已翻译好的中文，不负责重译，不修改时间轴，不增删字幕条目。这样既能提升中文自然度，又能降低字幕结构被破坏的风险。

### 实现方式

主要涉及文件：

- `src/youtube_transcriber.py`
  - 新增 `polish_subtitle_translations_with_deepseek()`。
  - 新增 `should_polish_translation()` 和 DeepSeek 返回 JSON 校验逻辑。
  - `translate_subtitle_file()`、`transcribe_audio_unified()`、`process_youtube_video()`、本地音视频和批量处理函数增加 `enable_translation_polish` 参数。
  - Whisper 生成 SRT/VTT/ASS 时改为先统一翻译并可选润色，再写出三种格式，避免不同格式翻译结果不一致。
  - 开启润色时保存 `*_google.srt` 和 `*_polished.srt`，下游配音和字幕烧录默认使用润色版。

- `main.py`
  - 设置页增加润色开关。
  - 保存设置时写入 `TRANSLATION_POLISH_DEEPSEEK`。
  - 各处理入口和闲时队列参数增加 `enable_translation_polish`。
  - 独立字幕翻译线程和 AI 配音任务透传润色开关。

- `src/dubbing_engine.py`
  - `DubbingTask` 增加 `enable_translation_polish`。
  - AI 配音翻译字幕时传入该开关，保证配音使用润色后的中文字幕。

- `src/gui/workers/worker_thread.py`
  - 模块化 WorkerThread 同步润色参数，保持与 `main.py` 内嵌线程一致。

- `src/gui/workers/subtitle_thread.py`
  - 独立字幕翻译线程改为复用 `translate_subtitle_file()`，避免单独实现与主流程不一致。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\youtube_transcriber.py src\dubbing_engine.py src\gui\workers\worker_thread.py src\gui\workers\subtitle_thread.py
```

结果：编译通过。

### 遗留问题和后续计划

- DeepSeek 返回仍有小概率不是合法 JSON，目前按“失败块保留原翻译”处理。
- 润色强度当前固定为轻度，后续可以增加“轻度 / 标准 / 较强”选项。
- 当前主要面向中文字幕润色，其他目标语言暂不启用。
- 后续可以增加术语表输入，例如固定 `agent=智能体`、`prompt=提示词`。

## 2026-06-22：抖音下载默认不生成 JSON 元数据

### 更新内容

- 抖音下载默认不再保存 `_metadata.json` 文件。
- GUI 中“保存元数据”复选框默认改为未勾选。
- CLI 默认关闭 `save_metadata`。
- `DouyinVdExtractor.download_video()` 增加 `save_metadata` 参数，只有显式开启时才写入 JSON。

### 设计思路

普通用户下载抖音视频时主要需要视频文件，JSON 元数据会让下载目录变得杂乱，也容易让用户误以为产生了额外无用文件。因此把元数据保存改为可选能力，默认保持目录干净。

### 实现方式

主要涉及文件：

- `main.py`
  - 抖音下载页“保存元数据”默认取消勾选。

- `src/douyin/config.py`
  - 默认配置 `save_metadata` 改为 `False`。

- `src/douyin/downloader.py`
  - 调用 `DouyinVdExtractor.download_video()` 时传入当前配置的 `save_metadata`。

- `src/douyin/douyinvd_extractor.py`
  - 只有 `save_metadata=True` 时才保存 `_metadata.json`，并把 metadata 文件加入下载结果列表。

- `src/douyin_cli.py`
  - CLI 默认不保存 JSON 元数据，并更新帮助说明。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\douyin_cli.py src\douyin\config.py src\douyin\downloader.py src\douyin\douyinvd_extractor.py src\gui\workers\douyin_threads.py
git diff --check
```

结果：检查通过。

## 2026-06-22：新增 VideoHub 项目宣传文章

### 更新内容

- 新增 `docs/videohub_promotion_article.md`。
- 文章面向公众号、项目推广和普通用户阅读场景。
- 重点介绍 VideoHub 如何把视频变成字幕、笔记、摘要、配音和可复用资料。
- 覆盖 YouTube/本地音视频处理、字幕翻译、DeepSeek 润色、AI 配音、闲时队列、手机本地网页下载等当前核心能力。

### 设计思路

宣传文章不按 README 的说明书结构罗列功能，而是围绕用户场景展开：长视频不好检索、英文视频理解成本高、批量处理耗时间、手机无法直接使用桌面工具等。每个场景对应一个 VideoHub 的能力，让读者先理解为什么需要这个工具，再理解怎么使用。

### 实现方式

主要涉及文件：

- `docs/videohub_promotion_article.md`
  - 开头用收藏视频难复用的场景引入。
  - 中间按使用场景介绍功能。
  - 结尾说明技术实现、使用边界和项目地址。

### 验证结果

已确认文档已创建，内容为 Markdown 格式，可直接用于公众号、博客或项目介绍页二次编辑。
## 2026-07-06：字幕翻译备用方案、多目标语言和项目 Skills 同步

### 更新内容

- 字幕翻译默认仍使用 Google Translate；当 Google 返回 429、非 200 响应或网络异常时，自动尝试 DeepSeek/OpenAI 备用翻译。
- YouTube、本地音频、本地视频、批处理和闲时队列流程增加 `target_language` 参数，默认 `zh-CN`，支持 `zh-CN`、`zh-TW`、`en`、`ja`、`ko`、`ru`、`fr`、`de`、`es`、`it`、`pt`、`ar`。
- GUI 主流程增加目标语言下拉框，复用现有字幕翻译和字幕烧录逻辑。
- DeepSeek 字幕润色限定为中文目标语言，避免非中文字幕被中文润色逻辑处理。
- 同步更新 `.agents/skills/` 下 VideoHub 项目级 skills，修正过期入口、直播录制状态、抖音主页下载说明、字幕烧录入口和队列默认行为。
- README / README_en 增加项目级 skills 介绍，说明 `.agents/skills/` 的用途、适用场景和主要复用入口。

### 设计思路

Google 翻译失败时原逻辑会直接返回原文，外层无法判断失败，也无法触发备用方案。本次改为在主翻译入口中使用可抛错的 Google 调用模式，捕获失败后再走 DeepSeek/OpenAI，并保留大模型翻译失败时回退 Google 的既有路径。

目标语言继续使用旧参数 `translate_to_chinese` 作为“是否翻译字幕”的兼容开关，新增加 `target_language`，避免破坏已有队列、CLI 和 GUI 调用。

### 实现方式

主要涉及文件：
- `src/youtube_transcriber.py`
  - 增加目标语言映射、语言族判断和 Google -> DeepSeek/OpenAI fallback。
  - `transcribe_audio_unified()`、`create_bilingual_subtitles()`、YouTube/本地音视频/批量处理入口透传 `target_language`。
  - CLI 增加 `--target-language`。
- `main.py`
  - YouTube、本地音频、本地视频、批处理页面增加目标语言下拉框。
  - WorkerThread 和闲时队列参数同步透传 `target_language`。
- `src/gui/workers/worker_thread.py`
  - 模块化 WorkerThread 同步目标语言参数。
- `.agents/skills/*/SKILL.md`
  - 同步当前项目入口、功能边界和最新字幕翻译/字幕烧录行为。
- `README.md`、`README_en.md`
  - 增加项目级 skills 说明，并修正英文 README 中过期限制描述。

### 验证结果

已执行：

```bash
python -m py_compile main.py src\youtube_transcriber.py src\gui\workers\worker_thread.py
git diff --check -- README.md README_en.md .agents/skills
```

另外通过 monkeypatch smoke test 模拟 Google 429，确认 `translate_text()` 会进入 DeepSeek/OpenAI fallback 分支。

### 遗留问题

- DeepSeek/OpenAI 备用翻译依赖对应 API key；未配置时仍会保留原文并输出日志。
- 非中文目标语言暂不执行 DeepSeek 润色。
- `docs/videohub_promotion_article.md` 当前仍是未跟踪文件，本次提交不纳入。
## 2026-08-08：《妻子变成小学生》全 10 集 50 分钟纯解说合集

### 更新内容

- 新建 `workspace/project076_wife_elementary_school_s01_complete_50min_commentary` 独立项目。
- 将已完成的 10 集素材重新组织为每集 5 分钟、总长 50 分钟的连续合集。
- 全程使用 MiniMax `speech-2.8-turbo`、`Chinese (Mandarin)_Male_Announcer`、1.2x 旁白，不映射原视频音轨。
- 讲解字幕统一置顶，避开源视频底部硬字幕。
- 生成 9:16、3:4、4:3、16:9 系列封面、章节、发布文案和发布包。

### 设计与实现

- 每集拆为 5 个一分钟叙事章节，每章使用 4 个约 15 秒的剧情证据画面，避免简单按比例抽帧造成画面与旁白错位。
- TTS 按章节缓存；每章保留约 0.4 秒起始呼吸，语音填充约 58.8 秒，后续修改可只重做对应章节。
- 最终视频通过硬链接进入发布包，避免在磁盘空间紧张时复制 1.3 GB 成片。
- 封面复用单集系列底图，以独立红色徽标突出“全10集”，保证主页小缩略图可辨认。

### 验证结果

- 最终时长 3000.021 秒，视频流 1、音频流 1。
- `silencedetect=noise=-42dB:d=3.0` 未发现 3 秒及以上静音。
- 11 个跨集时间点抽帧检查通过：顶部讲解字幕、底部源片字幕未重叠，无黑屏或文字越界。
- 发布包视频与主成片 SHA-256 一致：`c3c01d55cd4296e62089babf810ad2843d23f3f2a7df122e79e44c8a4045ab21`。

### 已知边界

- 源片包含底部硬字幕，无法从画面中移除；本合集通过把讲解字幕置顶来分层。
- 当前为 1080p 横版合集，未额外渲染竖版视频；发布包已提供多画幅封面。

## 2026-08-09：油画解说画框垂直居中与批量重渲染

### 更新内容

- 修复 `workspace/project071_oil_painting_commentary_series` 中油画主体整体偏上的问题。
- 将 Remotion 画作舞台从固定 `top: 190px` 改为根据 1920px 画布和 1188px 舞台高度自动计算，舞台顶部为 366px、中心为 960px。
- 进度条和动态字幕位置改为从画作舞台底部推导，避免分别维护多个无关的硬编码偏移。
- 重渲染第 3 至第 12 期；第 2 期《宫娥》已发布成片保持不变。
- 批量渲染脚本新增期数范围、强制覆盖、并发和原子临时文件参数，失败时不会覆盖已存在的正式成片。

### 设计与实现

- 居中在 Remotion 组合层完成，不使用 FFmpeg 对最终成片做二次位移，确保预览、渲染和后续模板复用保持一致。
- 每期原有旁白、音轨、字幕、时间轴、局部缩放和焦点参数不变，只调整公共画面布局。
- 已存在的 `clean_raw`、`clean_final` 别名同步为新成片的硬链接，防止旧别名继续指向未居中的版本。

### 验证结果

- `python -m py_compile scripts/render_series.py` 与 `npx tsc --noEmit` 通过。
- `python scripts/qa_series.py` 为 11/11 PASS：完整解码、1080x1920 H.264、AAC、持续黑场和封面尺寸检查均通过。
- 第 3 至第 12 期逐期抽取中段画面进行视觉检查，画作长方形上下边界一致，中心均为 960px，未与进度条、字幕或底栏重叠。
- 居中参数和视觉证据记录在项目 `docs/qa_recenter/recenter_qa.md`。
## 2026-08-12：付费支持无密钥环境预检与结构化申请

### 更新内容

- 新增 `src/support_preflight.py`，生成 JSON 与 Markdown 环境报告，覆盖 Python、FFmpeg/FFprobe、关键依赖、仓库文件、磁盘空间和目录可写性。
- 新增 `SUPPORT_REQUEST.md` 中英文申请模板，把服务档位、输入、输出、授权样例、日期和第三方费用偏好结构化。
- README 中英文版及 `SERVICES.md` 增加预检命令和申请入口。
- `.gitignore` 排除 `videohub_support_report*.json` 与 `videohub_support_report*.md`，避免机器环境信息进入版本库。

### 设计思路

QuickStart 的首次沟通成本主要来自无法复现的环境描述。预检只做本地、可审计检查，不联网、不扫描媒体、不调用付费 API；凭据只报告“是否配置”，不读取到输出。路径只保留 `<repo>` / `<home>` 后缀或可执行文件名。

目录可写性通过 3 秒硬超时子进程探测，防止权限异常或文件系统问题让整个客户报告无响应。预检失败仍输出完整报告，并使用非零退出码提醒客户处理 FAIL 项。

### 验证结果

- `python -B -m unittest discover -s tests -p 'test_support_preflight.py' -v`：5/5 PASS。
- 沙箱账户真实运行：24 PASS、2 FAIL；正确识别仓库与 workspace 不可写，未卡住。
- 普通 Windows 用户权限真实运行：26 PASS、0 WARN、0 FAIL，readiness 为 `ready`。
- 用当前 `.env` 值做哨兵扫描：报告中的密钥值泄露数为 0。
- `git check-ignore` 确认两类生成报告均被忽略；`git diff --check` 通过。

### 已知边界

- 预检不验证第三方 API 余额、账号权限、网络可达性、GPU 性能或特定素材兼容性。
- `ready` 只表示本地基础检查通过，不代表自动接单或承诺某个处理速度。
- 客户发送报告前仍应自行打开复核，不应附带 `.env` 或任何密钥文件。

## 2026-08-21：README 作品展示短样片

### 更新内容

- 从五个已完成项目中截取日本风景卡点、《妻子变成小学生》、《晚酌的流派》、《豺狼的日子》和《金特务：本色回归》短样片。
- 中英文 README 前部新增“作品展示 / Showcase”区域，使用可点击缩略图直接打开仓库内 MP4。
- `.gitignore` 仅对白名单目录 `docs/assets/showcase/` 放行压缩后的 JPG 和 MP4，其余运行时媒体继续保持忽略。

### 设计思路

展示区沿用 GitHub README 常见的“缩略图加视频链接”方式，不依赖浏览器自动播放，避免首屏同时加载多个视频。样片控制在约 11–17 秒、720p，并在文字中明确其用途只是展示工作流效果和素材授权边界。缩略图采用统一的 16:9 比例与居中播放标识，保证桌面端和移动端都能辨认。

### 实现方式

- 使用 FFmpeg 从现有成片中截取代表性段落，统一转码为 H.264、AAC、`yuv420p` 和 Fast Start MP4。
- 每个样片生成 640×360 JPG 缩略图，并叠加统一的播放按钮。
- README 使用 HTML 表格实现五项展示，中文和英文版本共用同一组媒体资产，避免重复占用仓库空间。

### 验证结果

- 五个 MP4 均完成 FFmpeg 全量解码检查，无损坏帧或解码错误。
- 所有样片均为 1280×720、H.264 视频和 AAC 音频，单文件最大约 3.1 MB，总媒体体积低于 7 MB。
- 五张缩略图已逐张检查，播放标识居中，画面可辨认。
- `git check-ignore` 验证仅展示目录媒体被放行，其他 JPG、MP4 忽略规则保持有效。

### 已知边界

- GitHub README 不直接内嵌播放 MP4；用户需要点击缩略图进入视频文件页面播放或下载。
- 样片来自既有项目成片，仅用于功能演示。仓库不声明拥有原始影视、音乐或画面素材的版权，发布者仍需自行确认素材授权。

## 2026-08-21：作品展示在线播放修复

### 更新内容

- 新增 `docs/showcase/index.html` 静态播放器，通过查询参数选择五个既有展示样片。
- 中英文 README 的封面链接由仓库 MP4 文件页改为 GitHub Pages 播放器地址。
- GitHub Pages 使用 `main` 分支的 `/docs` 目录发布，不重复上传视频文件。

### 原因与设计

GitHub 仓库 `blob` 地址返回 HTML 文件查看页；`raw.githubusercontent.com` 对仓库 MP4 返回 `application/octet-stream` 和 `X-Content-Type-Options: nosniff`，浏览器会下载文件而不是可靠地调用视频播放器。修复方式与参考项目一致：让 README 只展示缩略图，点击后进入独立的静态 HTML5 播放器。

播放器只接受代码中列出的五个文件名，查询参数无法拼接任意路径。视频继续保存在 `docs/assets/showcase/`，页面通过相对路径读取，减少重复资产和维护成本。

### 验证结果

- 本地静态服务返回播放器页面 `200 text/html`，MP4 返回 `200 video/mp4`。
- 内联 JavaScript 语法检查通过，五个视频文件名均存在于播放器白名单映射中。
- HTML5 `video` 使用 `controls`、`playsinline` 和 `preload="metadata"`，页面在 760px 与 440px 两个断点调整布局。
- `git diff --check` 通过；发布后继续检查 Pages 页面、媒体响应头及 README 的五个入口。

### 已知边界

- GitHub Pages 首次启用或新提交发布通常需要短暂构建时间，期间地址可能暂时返回 404。
- 浏览器不会强制带声音自动播放，用户仍需点击播放器的播放按钮。

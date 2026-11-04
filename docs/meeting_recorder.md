# 会议翻译与录屏（Windows源码功能）

从桌面端“会议翻译与录屏”打开独立录制窗口。支持选择整块屏幕或固定区域、录制系统播放声音、可选英文→中文悬浮字幕，停止后生成可直接进入视频学习的工程。原有MeetingCaption程序保持独立可用。

## 环境

VideoHub主程序继续使用PyQt6；会议窗口使用独立PySide6环境，不向主程序强装另一套Qt依赖。

已安装MeetingCaption时，会查找仓库上级目录的`MeetingCaption/.venv/Scripts/pythonw.exe`和其`models/`；也可以显式配置：

```powershell
$env:VIDEOHUB_MEETING_PYTHON = "F:\work\MeetingCaption\.venv\Scripts\pythonw.exe"
$env:VIDEOHUB_MEETING_MODELS = "F:\work\MeetingCaption\models"
python main.py
```

没有现成环境时，在仓库根目录创建可选环境（建议Python 3.11或3.12）：

```powershell
python -m venv .venv-meeting
.venv-meeting\Scripts\python.exe -m pip install -r requirements-meeting.txt
```

本地模型默认放到`workspace/models/meeting/`，也可通过上述变量指定已有模型目录：

```text
models/meeting/
  whisper/    # faster-whisper small.en，需含model.bin/config.json/tokenizer等完整文件
  translate/  # CTranslate2 OPUS-MT en-zh，含model.bin/source.spm/target.spm等
```

可复用原MeetingCaption已验证的模型；来源为[Whisper small.en](https://huggingface.co/Systran/faster-whisper-small.en)、[OPUS-MT en-zh CTranslate2](https://huggingface.co/gaudi/opus-mt-en-zh-ctranslate2)。不把模型或密钥加入Git。模块不自动下载模型；关闭实时字幕时，录制本身不加载识别/翻译模型。

FFmpeg使用VideoHub现有配置，需要`ffmpeg.exe`和同目录`ffprobe.exe`。本机验证版本为6.0，含gdigrab、libx264和AAC；不要求显卡硬件编码。

也可独立启动，不依赖桌面GUI：

```powershell
.venv-meeting\Scripts\python.exe -m src.meeting --models "F:\models\meeting" --ffmpeg "D:\ffmpeg\bin\ffmpeg.exe"
```

## 录制

1. 填写工程名称、保存目录；默认在`workspace/meetings/`按时间建立新目录，不覆盖已有工程。
2. 选择屏幕；固定区域的X/Y/宽/高使用相对所选屏幕的**物理像素**，不是Windows缩放后的界面坐标。最小128×128，宽高自动取偶数；超出屏幕则拒绝开始。多屏支持负坐标；显示器配置改变后重新打开会议窗口。
3. 选择和会议软件一致的扬声器/耳机。记录该设备的全部播放声音；首版不采集麦克风，也不只针对会议进程。
4. 如需字幕，勾选实时英译中；可只显示中文或同时显示英文。默认关闭，避免打开软件就启动识别或发送文字。
5. 点击开始，三秒倒计时可取消。开始后锁定设备和范围，显示录制时长。字幕浮窗可拖动。
6. 点击停止，或从系统托盘菜单停止。等待封装完成后再关闭窗口。首版不提供暂停续录或麦克风混音。

使用Windows窗口捕获排除机制，将录制控制窗和字幕窗从成片中排除；系统不支持时隐藏字幕并最小化控制面板，可通过托盘停止。会保留无烧录字幕的录像，中英字幕另存，避免学习页叠加重复字幕。具体显示驱动/缩放环境仍需现场确认。

## 实时翻译与保存

默认本地Whisper small.en（CPU int8）识别英文，OPUS-MT本地翻译。翻译设置也提供DeepSeek官方API，默认关闭思考模式；启用后仅将识别出的英文片段发送给所选模型，按API用量计费，不上传音频。设置保存不会发送测试请求。

密钥使用Windows当前用户DPAPI加密，保存到`%LOCALAPPDATA%/VideoHubMeeting/`；模型/方式在该目录的`translation.json`，密钥不进入工程和日志。与原MeetingCaption的设置分别保存；可接受进程已有`DEEPSEEK_API_KEY`。接口失败不静默换服务。

原始画面/声音持续录制，实时字幕使用独立的两段队列。字幕来不及会跳过旧片段并提示；翻译/模型失败只暂停实时字幕，录制继续。录音写入跟不上或设备溢出会停止录制并标记未完成，不把缺段音频当完整录音。

## 工程与会后学习

```text
workspace/meetings/<时间_名称_标识>/
  meeting.mp4                   # 浏览器可播放的H.264/AAC成片
  meeting.json                  # 录制状态、范围、音画起点与时钟校正
  videohub_learning.json        # 兼容现有视频学习目录导入
  live-captions.json            # 实时识别记录，可能有缺段
  subtitles/
    meeting.live.source.en.srt
    meeting.live.target.zh-CN.srt
    meeting.full.source.en.<内容标识>.srt       # 可选会后完整版本
    meeting.full.target.zh-CN.<内容标识>.srt
  originals/
    screen.mkv                  # 原始屏幕画面，保留供恢复
    system-audio.mka            # 连续无损FLAC录音，含静音
```

实时字幕必须视为草稿。停止后可直接“在视频学习中打开”，使用现有字幕、问答、笔记、大纲和脑图。若要完整复盘，选择“会后完整转写并翻译”，从连续原始录音重新识别，之后生成独立中英文版本。完整转写保留旧字幕，采用内容标识避免覆盖；翻译失败时保留已完成的完整原文。

会后处理使用当前翻译设置。DeepSeek模式开始前会提示将发送全部识别出的英文并产生API费用；可取消，已完成原文保留。已打开过学习页的工程不会强行改变用户所选轨道，处理后请在“字幕版本”选择`meeting.full`原文和译文。

录像和FLAC原始音频都会占用磁盘。原始媒体不自动删除，会议目录在批量清理中受保护。

## 恢复与同步

录制先保存Matroska原始文件，停止后再生成MP4。意外中断可点击“恢复未完成录制”，选择原工程目录重新封装；原始媒体保持不变。不保证修复操作系统或磁盘未写入的数据，损坏文件不会被显示为成功。

音画起点使用FFmpeg原生微秒时间戳与音频采样起点，避免科学计数法显示精度造成偏移；停止时校正小幅声卡时钟差异。超过2%的偏差会拒绝自动拉伸并保留原始文件。字幕时间同步裁剪到成片边界。

## 验证范围

- 会议工程、原声保存与字幕队列隔离、写入溢出、原生时间戳、分段语言、学习导入、可选运行环境、API错误与密钥加密均有自动回归。
- 独立Qt检查覆盖启动不采集、取消倒计时、越界区域、录制控件锁定、会后按钮和停止后旧字幕不显示。自有Qt界面渲染已检查中文字体。
- 17.3秒合成画面/注入测试语音完成实际FFmpeg封装，音视频均17.3秒；本地模型真实完成全文转写/翻译并导入学习库。测试窗口坐标暴露DPI缩放差异，不能据此声称各缩放比例的范围选择已完成视觉验收。
- 一小时合成视频/静音输入通过起点偏移和声卡时钟校正封装，输出音视频均3600秒；这不是一小时真实桌面/WASAPI耐久测试。
- 未使用真实会议内容或真实DeepSeek请求验收；真实设备长时采集、耳机切换、不同DPI/驱动组合需现场验证。现有EXE没有自动更新，需使用源码或另行打包。

开发检查：

```powershell
python -m pytest tests/test_meeting.py tests/test_meeting_translation.py -q
.venv-meeting\Scripts\python.exe tests/meeting_ui_checks.py
```

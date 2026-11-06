"""One local-file form for video, audio, text, and video directories."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

VIDEO_EXTENSIONS = frozenset({".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".3gp", ".mpg", ".mpeg"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"})
TEXT_EXTENSIONS = frozenset({".txt", ".md"})


class LocalFilesPanel(QWidget):
    process_requested = pyqtSignal()
    idle_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    extract_requested = pyqtSignal()
    songs_requested = pyqtSignal()

    def __init__(self, target_combo, songs_directory, parent=None):
        super().__init__(parent)
        self.busy = False
        layout = QVBoxLayout(self)
        self.input_group = QGroupBox("本地文件")
        inputs = QVBoxLayout(self.input_group)
        kind_row = QHBoxLayout()
        kind_row.addWidget(QLabel("文件类型:"))
        self.kind_combo = QComboBox()
        for title, kind in [("自动识别", "auto"), ("视频文件", "video"), ("音频文件", "audio"), ("文本文件", "text"), ("视频目录（批量）", "video_directory")]:
            self.kind_combo.addItem(title, kind)
        kind_row.addWidget(self.kind_combo)
        self.kind_label = QLabel()
        kind_row.addWidget(self.kind_label)
        kind_row.addStretch()
        inputs.addLayout(kind_row)
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("选择视频、音频、TXT / Markdown 文件，或包含视频的目录...")
        self.browse_button = QPushButton("选择文件...")
        self.directory_button = QPushButton("选择视频目录...")
        path_row.addWidget(self.path_input, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.directory_button)
        inputs.addLayout(path_row)
        layout.addWidget(self.input_group)

        self.options_group = QGroupBox("处理选项")
        options = QVBoxLayout(self.options_group)
        self.media_options = QWidget()
        media = QHBoxLayout(self.media_options)
        media.setContentsMargins(0, 0, 0, 0)
        steps = QVBoxLayout()
        self.transcription_checkbox = QCheckBox("执行转录（音频转文字）")
        self.transcription_checkbox.setChecked(True)
        self.subtitles_checkbox = QCheckBox("生成字幕文件")
        self.translate_checkbox = QCheckBox("翻译字幕")
        self.translate_checkbox.setChecked(True)
        for checkbox in (self.transcription_checkbox, self.subtitles_checkbox, self.translate_checkbox):
            steps.addWidget(checkbox)
        media.addLayout(steps)
        languages = QVBoxLayout()
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Whisper模型:"))
        self.whisper_combo = QComboBox()
        self.whisper_combo.addItems(["tiny", "base", "small", "medium", "large"])
        self.whisper_combo.setCurrentText("small")
        model_row.addWidget(self.whisper_combo)
        languages.addLayout(model_row)
        self.source_options = QWidget()
        source_row = QHBoxLayout(self.source_options)
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.addWidget(QLabel("源语言:"))
        self.source_combo = QComboBox()
        for title, code in [
            ("自动检测", "auto"), ("英语", "en"), ("中文", "zh"), ("日语", "ja"), ("韩语", "ko"),
            ("法语", "fr"), ("德语", "de"), ("西班牙语", "es"), ("意大利语", "it"), ("俄语", "ru"),
            ("阿拉伯语", "ar"), ("葡萄牙语", "pt"), ("荷兰语", "nl"), ("瑞典语", "sv"), ("丹麦语", "da"),
            ("挪威语", "no"), ("芬兰语", "fi"), ("波兰语", "pl"), ("捷克语", "cs"), ("匈牙利语", "hu"),
            ("泰语", "th"), ("越南语", "vi"), ("印尼语", "id"), ("马来语", "ms"), ("希腊语", "el"), ("土耳其语", "tr"),
        ]:
            self.source_combo.addItem(title, code)
        source_row.addWidget(self.source_combo)
        languages.addWidget(self.source_options)
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("目标语言:"))
        self.target_combo = target_combo
        target_row.addWidget(target_combo)
        languages.addLayout(target_row)
        media.addLayout(languages)
        options.addWidget(self.media_options)
        self.summary_checkbox = QCheckBox("生成文章摘要")
        self.summary_checkbox.setChecked(True)
        options.addWidget(self.summary_checkbox)
        self.text_hint = QLabel("文本文件直接生成文章摘要，使用设置页选择的模型。")
        self.text_hint.setWordWrap(True)
        options.addWidget(self.text_hint)
        self.video_options = QWidget()
        video = QVBoxLayout(self.video_options)
        video.setContentsMargins(0, 0, 0, 0)
        self.embed_checkbox = QCheckBox("将字幕嵌入到视频中")
        self.series_checkbox = QCheckBox("剧集项目模式（输出保存在视频目录）")
        self.series_checkbox.setChecked(True)
        self.series_checkbox.setToolTip("目录批处理时，将字幕、转写、摘要和工程清单保存在视频目录内")
        video.addWidget(self.embed_checkbox)
        video.addWidget(self.series_checkbox)
        options.addWidget(self.video_options)
        layout.addWidget(self.options_group)

        actions = QHBoxLayout()
        self.process_button = QPushButton("开始处理")
        self.stop_button = QPushButton("中断操作")
        self.idle_button = QPushButton("闲时操作")
        for button, signal in [(self.process_button, self.process_requested), (self.stop_button, self.stop_requested), (self.idle_button, self.idle_requested)]:
            button.setMinimumHeight(40)
            button.clicked.connect(lambda checked=False, target=signal: target.emit())
            actions.addWidget(button)
        layout.addLayout(actions)
        self.extract_group = QGroupBox("音频提取")
        extract = QHBoxLayout(self.extract_group)
        output_label = QLabel(f"输出目录: {songs_directory}")
        output_label.setWordWrap(True)
        extract.addWidget(output_label, 1)
        self.extract_button = QPushButton("提取音频到歌曲目录")
        self.songs_button = QPushButton("打开歌曲目录")
        extract.addWidget(self.extract_button)
        extract.addWidget(self.songs_button)
        layout.addWidget(self.extract_group)
        log_group = QGroupBox("处理日志")
        log = QVBoxLayout(log_group)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        log.addWidget(self.output_text)
        layout.addWidget(log_group, 1)

        self.path_input.textChanged.connect(self.refresh_kind)
        self.kind_combo.currentIndexChanged.connect(self.refresh_kind)
        self.browse_button.clicked.connect(self.browse_file)
        self.directory_button.clicked.connect(self.browse_directory)
        self.extract_button.clicked.connect(lambda: self.extract_requested.emit())
        self.songs_button.clicked.connect(lambda: self.songs_requested.emit())
        self.set_busy(False)

    def input_kind(self):
        selected = self.kind_combo.currentData()
        if selected != "auto":
            return selected
        value = self.path_input.text().strip()
        if not value:
            return "unknown"
        path = Path(value)
        if path.is_dir():
            return "video_directory"
        for kind, extensions in [("video", VIDEO_EXTENSIONS), ("audio", AUDIO_EXTENSIONS), ("text", TEXT_EXTENSIONS)]:
            if path.suffix.lower() in extensions:
                return kind
        return "unknown"

    def is_video_directory(self):
        return self.input_kind() == "video_directory"

    def validate_input(self):
        value = self.path_input.text().strip()
        if not value:
            raise ValueError("请先选择本地文件或视频目录")
        path, kind = Path(value), self.input_kind()
        if kind == "video_directory":
            if not path.is_dir():
                raise ValueError("请选择有效的视频目录")
            return kind
        if not path.is_file():
            raise ValueError("请选择有效的本地文件")
        extensions = {"video": VIDEO_EXTENSIONS, "audio": AUDIO_EXTENSIONS, "text": TEXT_EXTENSIONS}.get(kind)
        if not extensions:
            raise ValueError("无法识别文件类型，请选择支持的视频、音频或 TXT / Markdown 文件")
        if path.suffix.lower() not in extensions:
            raise ValueError("文件与所选类型不一致，请选择“自动识别”或正确的文件类型")
        return kind

    def refresh_kind(self, *_):
        kind = self.input_kind()
        video = kind in {"video", "video_directory"}
        self.kind_label.setText({"unknown": "按文件类型显示选项", "video": "视频：转写、字幕与摘要", "audio": "音频：转写、字幕与摘要", "text": "文本：生成摘要", "video_directory": "视频目录：批量处理"}[kind])
        self.media_options.setVisible(kind != "text")
        self.summary_checkbox.setVisible(kind != "text")
        self.text_hint.setVisible(kind == "text")
        self.source_options.setVisible(video)
        self.video_options.setVisible(video)
        self.series_checkbox.setVisible(kind == "video_directory")
        self.extract_group.setVisible(video)

    def set_busy(self, busy):
        self.busy = busy
        self.input_group.setEnabled(not busy)
        self.options_group.setEnabled(not busy)
        self.process_button.setEnabled(not busy)
        self.process_button.setText("处理中..." if busy else "开始处理")
        self.idle_button.setEnabled(not busy)
        self.extract_button.setEnabled(not busy)
        self.extract_button.setText("提取音频到歌曲目录")
        self.stop_button.setEnabled(busy)
        self.refresh_kind()

    def browse_file(self):
        filters = []
        for title, extensions in [("视频", VIDEO_EXTENSIONS), ("音频", AUDIO_EXTENSIONS), ("文本", TEXT_EXTENSIONS)]:
            patterns = " ".join("*" + ext for ext in sorted(extensions))
            filters.append(f"{title}文件 ({patterns})")
        all_patterns = " ".join("*" + ext for ext in sorted(VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | TEXT_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "选择本地文件", "", ";;".join([f"支持的文件 ({all_patterns})"] + filters))
        if path:
            self.kind_combo.setCurrentIndex(0)
            self.path_input.setText(path)

    def browse_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择包含视频文件的目录")
        if path:
            self.kind_combo.setCurrentIndex(0)
            self.path_input.setText(path)

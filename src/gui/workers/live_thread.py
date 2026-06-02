"""
直播录制线程
"""

from PyQt6.QtCore import QThread, pyqtSignal


class LiveRecordingThread(QThread):
    """直播录制线程"""
    log_signal = pyqtSignal(str)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.running = False
        self.paused = False

    def run(self):
        """运行直播录制"""
        self.running = True
        self.log_signal.emit("🔄 初始化直播录制系统...")

        try:
            # 导入直播录制适配器
            from live_recorder_adapter import get_live_recorder_manager

            # 获取直播录制管理器
            self.manager = get_live_recorder_manager()
            if not self.manager:
                self.log_signal.emit("❌ 直播录制管理器初始化失败")
                return

            # 设置日志回调
            self.manager.set_log_callback(self.log_signal.emit)

            # 获取URL列表
            urls = []
            for i in range(self.main_window.live_url_list.count()):
                url = self.main_window.live_url_list.item(i).text()
                if url and url.startswith('http'):
                    urls.append(url)

            if not urls:
                self.log_signal.emit("❌ 没有有效的直播间URL")
                return

            # 获取设置
            settings = {
                'interval': self.main_window.live_interval_spin.value(),
                'format': self.main_window.live_format_combo.currentText(),
                'quality': self.main_window.live_quality_combo.currentText(),
                'save_path': self.main_window.live_path_input.text(),
                'show_ffmpeg_log': self.main_window.show_ffmpeg_log.isChecked(),
                'save_log': self.main_window.save_log.isChecked()
            }

            # 开始监控
            success = self.manager.start_monitoring(urls, settings)
            if not success:
                self.log_signal.emit("❌ 启动监控失败")
                return

            # 保持线程运行，等待停止信号
            while self.running:
                self.msleep(1000)

        except Exception as e:
            self.log_signal.emit(f"❌ 直播录制系统错误: {str(e)}")
            import traceback
            traceback.print_exc()

        finally:
            # 停止监控
            if hasattr(self, 'manager') and self.manager:
                self.manager.stop_monitoring()
            self.log_signal.emit("🛑 直播录制监控已停止")

    def stop(self):
        """停止录制"""
        self.running = False
        self.log_signal.emit("🛑 正在停止直播录制...")

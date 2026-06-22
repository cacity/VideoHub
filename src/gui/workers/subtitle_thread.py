"""
字幕翻译线程
"""

import os
import shutil
from PyQt6.QtCore import QThread, pyqtSignal


class SubtitleTranslateThread(QThread):
    """字幕翻译工作线程"""
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.stopped = False

    def stop(self):
        """停止翻译"""
        self.stopped = True

    def run(self):
        """执行字幕翻译"""
        try:
            file_paths = self.params["file_paths"]
            target_language = self.params["target_language"]
            backup_original = self.params["backup_original"]

            total_files = len(file_paths)
            completed_files = 0
            failed_files = []

            self.update_signal.emit(f"开始翻译 {total_files} 个字幕文件...")

            for i, file_path in enumerate(file_paths):
                if self.stopped:
                    self.update_signal.emit("翻译已被用户停止")
                    break

                self.update_signal.emit(f"\n正在处理文件 {i+1}/{total_files}: {os.path.basename(file_path)}")
                self.progress_signal.emit(int((i / total_files) * 100), f"正在翻译: {os.path.basename(file_path)}")

                try:
                    # 备份原文件
                    if backup_original:
                        backup_path = file_path + ".backup"
                        shutil.copy2(file_path, backup_path)
                        self.update_signal.emit(f"已备份原文件: {backup_path}")

                    # 执行翻译
                    success = self.translate_single_file(file_path, target_language)

                    if success:
                        completed_files += 1
                        self.update_signal.emit(f"✅ 翻译完成: {os.path.basename(file_path)}")
                    else:
                        failed_files.append(file_path)
                        self.update_signal.emit(f"❌ 翻译失败: {os.path.basename(file_path)}")

                except Exception as e:
                    failed_files.append(file_path)
                    self.update_signal.emit(f"❌ 翻译出错: {os.path.basename(file_path)} - {str(e)}")

            if not self.stopped:
                # 计算成功率
                success_rate = (completed_files / total_files * 100) if total_files > 0 else 0

                self.update_signal.emit(f"\n{'='*50}")
                self.update_signal.emit(f"📊 翻译统计:")
                self.update_signal.emit(f"   总计: {total_files} 个文件")
                self.update_signal.emit(f"   成功: {completed_files} 个文件")
                self.update_signal.emit(f"   失败: {len(failed_files)} 个文件")
                self.update_signal.emit(f"   成功率: {success_rate:.1f}%")
                self.update_signal.emit(f"{'='*50}")

                if failed_files:
                    self.update_signal.emit(f"\n❌ 失败的文件:")
                    for f in failed_files:
                        self.update_signal.emit(f"   - {os.path.basename(f)}")

                # 发送完成信号
                all_success = len(failed_files) == 0
                self.finished_signal.emit(all_success, f"翻译完成: {completed_files}/{total_files}")

        except Exception as e:
            import traceback
            error_msg = f"翻译过程出错: {str(e)}\n{traceback.format_exc()}"
            self.update_signal.emit(f"❌ {error_msg}")
            self.finished_signal.emit(False, error_msg)

    def translate_single_file(self, file_path, target_language):
        """翻译单个字幕文件"""
        try:
            from youtube_transcriber import translate_subtitle_file

            result = translate_subtitle_file(
                file_path,
                target_language=target_language,
                enable_translation_polish=self.params.get("enable_translation_polish", False),
            )
            if result:
                self.update_signal.emit(f"已生成翻译文件: {result}")
                return True
            return False

        except Exception as e:
            self.update_signal.emit(f"翻译文件出错: {str(e)}")
            return False

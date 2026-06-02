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
            # 读取字幕文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析字幕条目
            from youtube_transcriber import parse_srt, format_srt_entry
            entries = parse_srt(content)

            if not entries:
                self.update_signal.emit(f"⚠️ 未找到有效的字幕条目: {os.path.basename(file_path)}")
                return False

            self.update_signal.emit(f"找到 {len(entries)} 个字幕条目")

            # 批量翻译文本
            texts_to_translate = [entry['text'] for entry in entries]

            # 使用 LLM 翻译
            from youtube_transcriber import translate_texts

            translated_texts = translate_texts(
                texts_to_translate,
                target_language=target_language,
                model=os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo'),
                api_key=os.getenv('OPENAI_API_KEY'),
                base_url=os.getenv('OPENAI_BASE_URL'),
                stream=False
            )

            if not translated_texts or len(translated_texts) != len(entries):
                self.update_signal.emit(f"⚠️ 翻译结果数量不匹配")
                return False

            # 更新字幕条目
            for i, entry in enumerate(entries):
                entry['text'] = translated_texts[i]

            # 生成新的字幕内容
            new_content = "\n\n".join([format_srt_entry(entry) for entry in entries])

            # 保存文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return True

        except Exception as e:
            self.update_signal.emit(f"翻译文件出错: {str(e)}")
            return False

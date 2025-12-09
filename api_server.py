"""
HTTP API服务器 - 为GUI应用提供REST API接口
供Chrome插件调用，实现队列管理功能
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import threading
from datetime import datetime
import logging

try:
    from PyQt6.QtCore import QTimer
except ImportError:
    QTimer = None

class APIServer:
    def __init__(self, main_window, port=8765):
        self.main_window = main_window
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)  # 允许跨域请求
        
        # 设置日志级别，减少Flask的输出
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        self.setup_routes()
        self.server_thread = None
        self.running = False

    def notify_status_bar(self, message, timeout=5000):
        """在GUI状态栏显示提示信息"""
        if not self.main_window:
            return

        status_bar = getattr(self.main_window, 'statusBar', None)
        if not status_bar:
            return

        def show_message():
            try:
                status_bar.showMessage(message, timeout)
                if hasattr(self.main_window, 'log_extension_event'):
                    self.main_window.log_extension_event(message)
            except Exception as err:
                print(f"API状态提示失败: {err}")

        try:
            if QTimer:
                QTimer.singleShot(0, show_message)
            else:
                show_message()
        except Exception as err:
            print(f"API状态通知异常: {err}")

    def setup_routes(self):
        """设置API路由"""

        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """健康检查接口"""
            return jsonify({
                'status': 'ok',
                'message': 'API server is running',
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/queue', methods=['GET'])
        def get_queue():
            """获取当前队列"""
            try:
                queue_data = {
                    'tasks': self.main_window.idle_tasks,
                    'idle_start_time': self.main_window.idle_start_time,
                    'idle_end_time': self.main_window.idle_end_time,
                    'is_idle_running': self.main_window.is_idle_running,
                    'idle_paused': self.main_window.idle_paused
                }
                return jsonify({
                    'success': True,
                    'data': queue_data
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/queue/add', methods=['POST'])
        def add_to_queue():
            """添加任务到队列"""
            try:
                data = request.get_json()
                print(f"API服务器: 收到添加到队列请求 {data}")
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No JSON data provided'
                    }), 400
                
                # 验证必需字段
                required_fields = ['platform', 'url', 'title']
                for field in required_fields:
                    if field not in data:
                        self.notify_status_bar(f"请求缺少字段: {field}")
                        return jsonify({
                            'success': False,
                            'error': f'Missing required field: {field}'
                        }), 400

                # 创建任务对象
                task = self.create_task_from_request(data)
                self.notify_status_bar(f"收到扩展任务: {task['title']}")

                # 检查是否已存在相同任务
                existing_task = self.find_existing_task(task)
                if existing_task:
                    self.notify_status_bar('任务已存在于队列中')
                    return jsonify({
                        'success': False,
                        'error': 'Task already exists in queue'
                    }), 409

                # 添加到队列
                self.main_window.idle_tasks.append(task)
                
                # 保存队列
                self.main_window.save_idle_queue()
                
                # 刷新GUI显示
                if hasattr(self.main_window, 'refresh_idle_queue_display'):
                    self.main_window.refresh_idle_queue_display()

                self.notify_status_bar(
                    f"扩展任务已加入队列，当前共有 {len(self.main_window.idle_tasks)} 个任务"
                )

                return jsonify({
                    'success': True,
                    'message': 'Task added to queue successfully',
                    'task_id': len(self.main_window.idle_tasks) - 1,
                    'queue_length': len(self.main_window.idle_tasks)
                })

            except Exception as e:
                self.notify_status_bar(f"处理扩展任务失败: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/queue/clear', methods=['DELETE'])
        def clear_queue():
            """清空队列"""
            try:
                self.main_window.idle_tasks = []
                self.main_window.save_idle_queue()
                
                # 刷新GUI显示
                if hasattr(self.main_window, 'refresh_idle_queue_display'):
                    self.main_window.refresh_idle_queue_display()
                
                return jsonify({
                    'success': True,
                    'message': 'Queue cleared successfully'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/queue/remove/<int:task_id>', methods=['DELETE'])
        def remove_task(task_id):
            """移除指定任务"""
            try:
                if 0 <= task_id < len(self.main_window.idle_tasks):
                    removed_task = self.main_window.idle_tasks.pop(task_id)
                    self.main_window.save_idle_queue()
                    
                    # 刷新GUI显示
                    if hasattr(self.main_window, 'refresh_idle_queue_display'):
                        self.main_window.refresh_idle_queue_display()
                    
                    return jsonify({
                        'success': True,
                        'message': 'Task removed successfully',
                        'removed_task': removed_task['title']
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'Invalid task ID'
                    }), 404
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/settings', methods=['GET'])
        def get_settings():
            """获取设置"""
            try:
                settings = {
                    'idle_start_time': self.main_window.idle_start_time,
                    'idle_end_time': self.main_window.idle_end_time,
                    'is_idle_running': self.main_window.is_idle_running,
                    'idle_paused': self.main_window.idle_paused
                }
                return jsonify({
                    'success': True,
                    'data': settings
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        @self.app.route('/api/settings', methods=['PUT'])
        def update_settings():
            """更新设置"""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({
                        'success': False,
                        'error': 'No JSON data provided'
                    }), 400
                
                # 更新设置
                if 'idle_start_time' in data:
                    self.main_window.idle_start_time = data['idle_start_time']
                if 'idle_end_time' in data:
                    self.main_window.idle_end_time = data['idle_end_time']
                
                # 保存设置
                self.main_window.save_idle_queue()
                
                return jsonify({
                    'success': True,
                    'message': 'Settings updated successfully'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
    
    def create_task_from_request(self, data):
        """从请求数据创建任务对象"""
        platform = data['platform']
        
        # 基础参数模板
        from paths_config import DEFAULT_SUMMARY_DIR
        base_params = {
            "model": None,
            "api_key": None,
            "base_url": None,
            "whisper_model_size": "small",
            "stream": True,
            "summary_dir": DEFAULT_SUMMARY_DIR,
            "download_video": True,
            "custom_prompt": None,
            "template_path": None,
            "generate_subtitles": True,
            "translate_to_chinese": False,
            "embed_subtitles": True,
            "cookies_file": None,
            "enable_transcription": False,
            "generate_article": False
        }
        
        # 根据平台创建任务
        if platform == 'youtube':
            task = {
                "type": "youtube",
                "params": {
                    **base_params,
                    "youtube_url": data['url']
                },
                "title": f"视频: {data['title'][:50]}..."
            }
        elif platform == 'twitter':
            task = {
                "type": "twitter",
                "params": {
                    **base_params,
                    "url": data['url'],
                    "author": data.get('author', ''),
                    "text": data.get('text', '')
                },
                "title": f"Twitter: {data['title'][:50]}..."
            }
        elif platform == 'bilibili':
            task = {
                "type": "bilibili",
                "params": {
                    **base_params,
                    "url": data['url'],
                    "uploader": data.get('uploader', ''),
                    "videoId": data.get('videoId', '')
                },
                "title": f"B站: {data['title'][:50]}..."
            }
        else:
            raise ValueError(f"Unsupported platform: {platform}")
        
        # 添加元数据
        task["platform"] = platform
        task["addedTime"] = datetime.now().isoformat()
        task["addedVia"] = "chrome_extension"
        
        return task
    
    def find_existing_task(self, new_task):
        """检查是否存在相同的任务"""
        new_url = new_task['params'].get('youtube_url') or new_task['params'].get('url')
        
        for task in self.main_window.idle_tasks:
            existing_url = task['params'].get('youtube_url') or task['params'].get('url')
            if existing_url == new_url:
                return task
        return None
    
    def start_server(self):
        """启动API服务器"""
        if self.running:
            return
        
        def run_server():
            try:
                print(f"启动API服务器，监听端口 {self.port}")
                self.app.run(
                    host='127.0.0.1',
                    port=self.port,
                    debug=False,
                    use_reloader=False,
                    threaded=True
                )
            except Exception as e:
                print(f"API服务器启动失败: {e}")
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.running = True
        print(f"API服务器已启动: http://127.0.0.1:{self.port}")
    
    def stop_server(self):
        """停止API服务器"""
        if self.running:
            self.running = False
            print("API服务器已停止")

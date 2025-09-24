#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能Selenium提取器 - 自动处理ChromeDriver和Chrome安装
"""

import time
import json
import re
import os
import subprocess
import platform
from typing import Optional, Dict, Any, Callable
from urllib.parse import unquote

class SmartSeleniumExtractor:
    """智能Selenium提取器，自动处理各种环境问题"""
    
    def __init__(self):
        self.driver = None
        self._selenium_available = None
        self._chrome_available = None
        self._driver_path = None
        
    def _check_selenium(self) -> bool:
        """检查Selenium是否可用"""
        if self._selenium_available is not None:
            return self._selenium_available
            
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            self._selenium_available = True
            print("✅ Selenium 模块可用")
            return True
        except ImportError:
            print("❌ Selenium 未安装")
            self._selenium_available = False
            return False
    
    def _check_chrome(self) -> bool:
        """检查Chrome是否可用"""
        if self._chrome_available is not None:
            return self._chrome_available
        
        # 检查各种Chrome可执行文件
        chrome_commands = [
            'google-chrome',
            'chromium-browser', 
            'chromium',
            '/usr/bin/google-chrome',
            '/usr/bin/chromium-browser',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            'chrome.exe',
        ]
        
        for cmd in chrome_commands:
            try:
                result = subprocess.run([cmd, '--version'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"✅ 找到Chrome: {result.stdout.strip()}")
                    self._chrome_available = True
                    return True
            except:
                continue
        
        print("❌ 未找到Chrome浏览器")
        self._chrome_available = False
        return False
    
    def _setup_webdriver_manager(self):
        """使用webdriver-manager自动管理ChromeDriver"""
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            print("🔧 使用webdriver-manager自动配置ChromeDriver...")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-plugins')
            chrome_options.add_argument('--disable-images')
            chrome_options.add_argument('--disable-javascript')  # 暂时禁用JS减少资源消耗
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # 尝试自动下载和配置ChromeDriver
            driver_path = ChromeDriverManager().install()
            print(f"📍 ChromeDriver路径: {driver_path}")
            
            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
            
            print("✅ webdriver-manager配置成功")
            return True
            
        except Exception as e:
            print(f"❌ webdriver-manager配置失败: {e}")
            return False
    
    def _setup_local_chromedriver(self):
        """使用本地ChromeDriver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            # 检查本地ChromeDriver文件
            possible_paths = [
                "./chromedriver",
                "./chromedriver.exe", 
                "/usr/local/bin/chromedriver",
                "/usr/bin/chromedriver"
            ]
            
            chromedriver_path = None
            for path in possible_paths:
                if os.path.exists(path) and os.access(path, os.X_OK):
                    chromedriver_path = path
                    break
            
            if not chromedriver_path:
                print("❌ 未找到本地ChromeDriver")
                return False
            
            print(f"📍 使用本地ChromeDriver: {chromedriver_path}")
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
            
            print("✅ 本地ChromeDriver配置成功")
            return True
            
        except Exception as e:
            print(f"❌ 本地ChromeDriver配置失败: {e}")
            return False
    
    def _init_driver(self):
        """智能初始化Chrome驱动"""
        if not self._check_selenium():
            return False
        
        # 首先检查Chrome是否可用
        if not self._check_chrome():
            print("⚠️ Chrome浏览器不可用，无法使用Selenium")
            return False
        
        # 尝试不同的配置方法
        setup_methods = [
            ("webdriver-manager自动配置", self._setup_webdriver_manager),
            ("本地ChromeDriver", self._setup_local_chromedriver),
        ]
        
        for method_name, method in setup_methods:
            try:
                print(f"🔄 尝试 {method_name}...")
                if method():
                    print(f"✅ {method_name} 成功")
                    return True
            except Exception as e:
                print(f"❌ {method_name} 失败: {e}")
                continue
        
        print("❌ 所有ChromeDriver配置方法都失败")
        return False
    
    def extract_video_info_simple(self, url: str) -> Optional[Dict[str, Any]]:
        """
        简化版视频信息提取 - 专注于获取核心数据
        """
        if not self._init_driver():
            return None
            
        try:
            print(f"🌐 简化Selenium提取: {url}")
            
            # 快速加载页面
            self.driver.get(url)
            time.sleep(3)  # 减少等待时间
            
            current_url = self.driver.current_url
            page_source = self.driver.page_source
            
            print(f"🔗 最终URL: {current_url}")
            print(f"📄 页面长度: {len(page_source)}")
            
            # 提取视频ID
            video_id_match = re.search(r'/video/(\d+)', current_url)
            video_id = video_id_match.group(1) if video_id_match else "unknown"
            
            # 快速查找视频数据
            video_info = {
                'aweme_id': video_id,
                'desc': '未知标题',
                'duration': 0,
                'create_time': int(time.time()),
                'author': {
                    'uid': '',
                    'nickname': '未知用户',
                    'unique_id': '',
                    'avatar_url': '',
                },
                'video': {
                    'play_url': '',
                    'play_url_no_watermark': '',
                    'cover_url': '',
                    'width': 0,
                    'height': 0,
                    'duration': 0,
                },
                'statistics': {
                    'digg_count': 0,
                    'comment_count': 0,
                    'share_count': 0,
                    'play_count': 0,
                },
                'music': {
                    'id': '',
                    'title': '',
                    'author': '',
                    'play_url': '',
                },
                'extraction_method': 'smart_selenium',
                'from_selenium': True
            }
            
            # 快速提取标题
            try:
                title_element = self.driver.find_element("tag name", "title")
                if title_element:
                    title = title_element.get_attribute("text") or title_element.text
                    if title and "抖音" not in title:
                        video_info['desc'] = title[:100]  # 限制长度
                        print(f"📝 提取标题: {title[:50]}...")
            except:
                pass
            
            # 查找视频URL - 使用JavaScript执行
            try:
                # 执行JavaScript查找视频元素
                video_elements = self.driver.execute_script("""
                    var videos = document.querySelectorAll('video');
                    var urls = [];
                    for (var i = 0; i < videos.length; i++) {
                        if (videos[i].src) {
                            urls.push(videos[i].src);
                        }
                    }
                    return urls;
                """)
                
                if video_elements:
                    video_url = video_elements[0]
                    video_info['video']['play_url'] = video_url
                    video_info['video']['play_url_no_watermark'] = video_url
                    print(f"🎬 JS提取视频URL: {video_url[:80]}...")
                
            except Exception as e:
                print(f"⚠️ JS提取视频URL失败: {e}")
            
            # 如果JS方法失败，使用正则表达式
            if not video_info['video']['play_url']:
                video_urls = self._find_video_urls_regex(page_source)
                if video_urls:
                    video_info['video']['play_url'] = video_urls[0]
                    video_info['video']['play_url_no_watermark'] = video_urls[0]
                    print(f"🎬 正则提取视频URL: {video_urls[0][:80]}...")
            
            return video_info
            
        except Exception as e:
            print(f"❌ 简化Selenium提取失败: {e}")
            return None
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    self.driver = None
                except:
                    pass
    
    def _find_video_urls_regex(self, page_source: str) -> list:
        """使用正则表达式查找视频URL"""
        video_urls = []
        
        patterns = [
            r'https://[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'"src":"([^"]*\.mp4[^"]*)"',
            r'src="([^"]*\.mp4[^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_source)
            for match in matches:
                url = match if isinstance(match, str) else match[0] if match else ""
                if url and url.startswith('http') and '.mp4' in url:
                    if 'douyin_pc_client.mp4' not in url:  # 过滤客户端下载链接
                        try:
                            url = unquote(url)
                        except:
                            pass
                        
                        if url not in video_urls:
                            video_urls.append(url)
        
        return video_urls
    
    def is_available(self) -> bool:
        """检查提取器是否可用"""
        return self._check_selenium() and self._check_chrome()
    
    def install_requirements(self) -> bool:
        """尝试安装必要的依赖"""
        try:
            import subprocess
            import sys
            
            print("📦 安装Selenium和webdriver-manager...")
            result = subprocess.run([
                sys.executable, '-m', 'pip', 'install', 
                'selenium', 'webdriver-manager'
            ], capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                print("✅ 依赖安装成功")
                self._selenium_available = None  # 重置状态
                return self._check_selenium()
            else:
                print(f"❌ 依赖安装失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ 依赖安装异常: {e}")
            return False
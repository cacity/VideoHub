#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
基于Selenium的抖音视频提取器
这是经过测试的有效方案
"""

import time
import json
import re
import os
from typing import Optional, Dict, Any, Callable
from urllib.parse import unquote

class SeleniumExtractor:
    """基于Selenium的抖音视频提取器"""
    
    def __init__(self):
        self.driver = None
        self._selenium_available = None
        
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
    
    def _init_driver(self):
        """初始化Chrome驱动"""
        if not self._check_selenium():
            return False
            
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            import platform
            
            # 根据操作系统配置ChromeDriver路径
            system = platform.system()
            if system == "Windows":
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                chromedriver_path = os.path.join(current_dir, "chromedriver.exe")
                
                # 检查ChromeDriver是否存在
                if not os.path.exists(chromedriver_path):
                    print(f"❌ ChromeDriver未找到: {chromedriver_path}")
                    print("请确保chromedriver.exe在当前目录下")
                    return False
                
                print(f"📍 使用ChromeDriver: {chromedriver_path}")
                service = Service(chromedriver_path)
            else:
                # Linux/WSL环境：尝试使用系统ChromeDriver或自动管理
                print("🐧 检测到Linux环境，尝试使用系统ChromeDriver...")
                try:
                    # 尝试使用webdriver-manager自动管理
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    print("✅ 使用webdriver-manager自动管理ChromeDriver")
                except ImportError:
                    # 如果没有webdriver-manager，尝试使用系统路径
                    print("⚠️ webdriver-manager未安装，尝试使用系统ChromeDriver")
                    service = None  # 让Selenium自动查找
            
            chrome_options = Options()
            # chrome_options.add_argument('--headless')  # 注释掉headless模式，让浏览器显示
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-logging')
            chrome_options.add_argument('--disable-gpu-sandbox')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-background-timer-throttling')
            chrome_options.add_argument('--disable-backgrounding-occluded-windows')
            chrome_options.add_argument('--disable-renderer-backgrounding')
            chrome_options.add_argument('--disable-features=TranslateUI')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--no-first-run')
            chrome_options.add_argument('--no-default-browser-check')
            chrome_options.add_argument('--log-level=3')
            chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # 初始化WebDriver
            if service:
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # 让Selenium自动查找ChromeDriver
                self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            print("✅ Chrome驱动初始化成功")
            return True
            
        except Exception as e:
            print(f"❌ Chrome驱动初始化失败: {e}")
            print("请检查:")
            print("1. Chrome浏览器是否已安装")
            print("2. chromedriver.exe版本是否与Chrome版本匹配")
            print("3. chromedriver.exe是否有执行权限")
            return False
    
    def extract_video_info(self, url: str, progress_callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        提取抖音视频信息
        :param url: 抖音视频链接
        :param progress_callback: 进度回调函数
        :return: 视频信息字典
        """
        if not self._init_driver():
            return None
            
        try:
            print(f"🌐 使用Selenium提取视频信息: {url}")
            if progress_callback:
                progress_callback(10, "启动浏览器...")
            
            # 加载页面
            print("📄 加载页面...")
            if progress_callback:
                progress_callback(30, "加载页面...")
                
            self.driver.get(url)
            time.sleep(8)  # 等待JavaScript执行
            
            # 尝试等待视频元素出现
            try:
                # 等待视频相关元素
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                wait = WebDriverWait(self.driver, 10)
                # 等待视频容器或播放按钮出现
                video_selectors = [
                    "video",
                    "[data-e2e='video-player']",
                    ".video-container",
                    ".player-container",
                    "div[id*='video']"
                ]
                
                for selector in video_selectors:
                    try:
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                        print(f"✅ 找到视频元素: {selector}")
                        break
                    except:
                        continue
                        
                # 额外等待确保JavaScript执行完成
                time.sleep(3)
                
            except Exception as e:
                print(f"⚠️ 等待视频元素时出错: {e}")
                # 继续执行，使用默认等待时间
                time.sleep(5)
            
            if progress_callback:
                progress_callback(60, "分析页面数据...")
            
            current_url = self.driver.current_url
            page_source = self.driver.page_source
            
            print(f"🔗 最终URL: {current_url}")
            print(f"📄 页面长度: {len(page_source)}")
            
            # 提取视频ID
            video_id_match = re.search(r'/video/(\d+)', current_url)
            video_id = video_id_match.group(1) if video_id_match else "unknown"
            
            # 查找视频相关数据
            video_info = self._extract_video_data(page_source, video_id)
            
            if progress_callback:
                progress_callback(90, "提取视频链接...")
            
            # 查找实际的视频文件链接
            video_urls = self._find_video_urls(page_source)
            
            if video_urls:
                print(f"🎬 发现 {len(video_urls)} 个视频链接")
                # 使用第一个非客户端下载的视频链接
                actual_video_url = None
                for video_url in video_urls:
                    if 'douyin_pc_client.mp4' not in video_url:
                        actual_video_url = video_url
                        break
                
                if not actual_video_url and video_urls:
                    actual_video_url = video_urls[0]
                
                if actual_video_url:
                    video_info['video']['play_url'] = actual_video_url
                    video_info['video']['play_url_no_watermark'] = actual_video_url
                    print(f"✅ 提取到实际视频链接: {actual_video_url[:80]}...")
            else:
                print("⚠️ 未找到直接的视频下载链接，但已获取视频基本信息")
                # 即使没有直接下载链接，也可以提供视频页面链接作为备用
                video_info['video']['play_url'] = url
                video_info['video']['page_url'] = current_url
            
            # 查找封面图片
            cover_urls = self._find_cover_urls(page_source)
            if cover_urls:
                video_info['video']['cover_url'] = cover_urls[0]
                print(f"🖼️ 提取到封面链接: {cover_urls[0][:80]}...")
            
            if progress_callback:
                progress_callback(100, "提取完成")
            
            # 标记为Selenium提取
            video_info['extraction_method'] = 'selenium'
            video_info['from_selenium'] = True
            
            return video_info
            
        except Exception as e:
            print(f"❌ Selenium提取失败: {e}")
            return None
        finally:
            if self.driver:
                try:
                    print("🔄 正在关闭浏览器...")
                    self.driver.quit()
                    self.driver = None
                    print("✅ 浏览器已关闭")
                except Exception as e:
                    print(f"⚠️ 关闭浏览器时出错: {e}")
                    try:
                        # 强制终止进程
                        import psutil
                        for proc in psutil.process_iter(['pid', 'name']):
                            if 'chrome' in proc.info['name'].lower():
                                proc.kill()
                    except:
                        pass
    
    def _extract_video_data(self, page_source: str, video_id: str) -> Dict[str, Any]:
        """从页面源码提取视频基本信息"""
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
            }
        }
        
        try:
            # 尝试提取标题
            title_patterns = [
                r'<title>([^<]+)</title>',
                r'"desc":"([^"]*)"',
                r'content="([^"]*)" name="description"',
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, page_source, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    if title and title != '抖音':
                        video_info['desc'] = title
                        print(f"📝 提取到标题: {title}")
                        break
            
            # 尝试提取作者信息
            author_patterns = [
                r'"nickname":"([^"]*)"',
                r'"author":"([^"]*)"',
                r'作者:([^,]*)',
            ]
            
            for pattern in author_patterns:
                match = re.search(pattern, page_source)
                if match:
                    author = match.group(1).strip()
                    if author:
                        video_info['author']['nickname'] = author
                        print(f"👤 提取到作者: {author}")
                        break
            
        except Exception as e:
            print(f"⚠️ 提取基本信息时出错: {e}")
        
        return video_info
    
    def _find_video_urls(self, page_source: str) -> list:
        """查找页面中的视频URL"""
        video_urls = []
        
        # 增强的视频URL模式，包含更多可能的格式
        patterns = [
            # 直接MP4链接
            r'https://[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'https://[^"\'>\s]*video[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'https://[^"\'>\s]*aweme[^"\'>\s]*\.mp4[^"\'>\s]*',
            # JSON格式的URL
            r'"play_url[^"]*":"([^"]*\.mp4[^"]*)"',
            r'"video_url[^"]*":"([^"]*\.mp4[^"]*)"',
            r'"url[^"]*":"([^"]*\.mp4[^"]*)"',
            r'"playUrl[^"]*":"([^"]*\.mp4[^"]*)"',
            r'"videoUrl[^"]*":"([^"]*\.mp4[^"]*)"',
            # HTML属性
            r'src="([^"]*\.mp4[^"]*)"',
            r'data-src="([^"]*\.mp4[^"]*)"',
            r'data-url="([^"]*\.mp4[^"]*)"',
            # 新的抖音视频URL格式
            r'https://[^"\'>\s]*v\.douyin\.com[^"\'>\s]*',
            r'https://[^"\'>\s]*aweme[^"\'>\s]*\.byteimg\.com[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'https://[^"\'>\s]*p[0-9]+\.douyinpic\.com[^"\'>\s]*\.mp4[^"\'>\s]*',
            # 更宽泛的模式
            r'"[^"]*url[^"]*":\s*"([^"]*(?:\.mp4|video)[^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_source)
            for match in matches:
                url = match if isinstance(match, str) else match[0] if match else ""
                if url and url.startswith('http') and '.mp4' in url:
                    # 解码URL
                    try:
                        url = unquote(url)
                    except:
                        pass
                    
                    if url not in video_urls:
                        video_urls.append(url)
        
        return video_urls
    
    def _find_cover_urls(self, page_source: str) -> list:
        """查找页面中的封面图片URL"""
        cover_urls = []
        
        patterns = [
            r'https://[^"\'>\s]*\.jpg[^"\'>\s]*',
            r'https://[^"\'>\s]*\.jpeg[^"\'>\s]*',
            r'https://[^"\'>\s]*\.png[^"\'>\s]*',
            r'https://[^"\'>\s]*\.webp[^"\'>\s]*',
            r'"cover":"([^"]*)"',
            r'"poster":"([^"]*)"',
            r'poster="([^"]*)"',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_source)
            for match in matches:
                url = match if isinstance(match, str) else match[0] if match else ""
                if url and url.startswith('http') and any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    # 过滤掉明显不是封面的图片
                    if not any(keyword in url.lower() for keyword in ['icon', 'logo', 'avatar', 'favicon']):
                        try:
                            url = unquote(url)
                        except:
                            pass
                        
                        if url not in cover_urls:
                            cover_urls.append(url)
        
        return cover_urls
    
    def is_available(self) -> bool:
        """检查提取器是否可用"""
        return self._check_selenium()
    
    def install_selenium(self) -> bool:
        """尝试安装Selenium"""
        try:
            import subprocess
            import sys
            print("📦 正在安装 Selenium...")
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', 'selenium'], 
                                  capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                print("✅ Selenium 安装成功")
                self._selenium_available = None  # 重置状态，重新检查
                return self._check_selenium()
            else:
                print(f"❌ Selenium 安装失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"❌ Selenium 安装异常: {e}")
            return False
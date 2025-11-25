#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
DLPanda.com 抖音视频提取器
使用 dlpanda.com 作为第三方服务下载抖音视频
"""

import requests
import re
import time
import json
from typing import Optional, Dict, Any, Callable
from urllib.parse import urljoin, urlparse

class DLPandaExtractor:
    """基于DLPanda.com的抖音视频提取器"""
    
    def __init__(self):
        self.base_url = "https://dlpanda.com"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def extract_video_info(self, url: str, progress_callback: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
        """
        从DLPanda提取抖音视频信息
        :param url: 抖音视频链接
        :param progress_callback: 进度回调函数
        :return: 视频信息字典
        """
        try:
            print(f"🐼 使用DLPanda提取视频信息: {url}")
            if progress_callback:
                progress_callback(10, "连接DLPanda服务...")
            
            # 步骤1: 获取主页面和token
            if progress_callback:
                progress_callback(20, "获取访问令牌...")
            
            token = self._get_token()
            if not token:
                print("❌ 无法获取访问令牌")
                return None
            
            # 步骤2: 提交视频URL
            if progress_callback:
                progress_callback(40, "提交视频链接...")
            
            video_data = self._submit_url(url, token)
            if not video_data:
                print("❌ 提交URL失败")
                return None
            
            if progress_callback:
                progress_callback(80, "解析视频信息...")
            
            # 步骤3: 解析返回的视频信息
            video_info = self._parse_video_data(video_data, url)
            
            if progress_callback:
                progress_callback(100, "提取完成")
            
            # 标记为DLPanda提取
            video_info['extraction_method'] = 'dlpanda'
            video_info['from_dlpanda'] = True
            
            return video_info
            
        except Exception as e:
            print(f"❌ DLPanda提取失败: {e}")
            return None
    
    def _get_token(self) -> Optional[str]:
        """获取页面token"""
        try:
            print("🔍 正在获取DLPanda页面...")
            response = self.session.get(self.base_url, timeout=10)
            response.raise_for_status()
            
            print(f"📄 页面响应状态: {response.status_code}")
            print(f"📄 页面长度: {len(response.text)}")
            
            # 多种token提取模式
            token_patterns = [
                r'name="t0ken"[^>]*value="([^"]*)"',
                r'id="token"[^>]*value="([^"]*)"',
                r'<input[^>]*name="t0ken"[^>]*value="([^"]*)"',
                r'<input[^>]*value="([^"]*)"[^>]*name="t0ken"',
                r't0ken["\']?\s*:\s*["\']([^"\']*)["\']',
                r'token["\']?\s*:\s*["\']([^"\']*)["\']'
            ]
            
            for i, pattern in enumerate(token_patterns):
                token_match = re.search(pattern, response.text, re.IGNORECASE)
                if token_match:
                    token = token_match.group(1).strip()
                    if token and len(token) > 3:  # 确保token不为空且有意义
                        print(f"✅ 获取到token (模式{i+1}): {token}")
                        return token
            
            # 如果都没找到，打印部分页面内容进行调试
            print("❌ 未找到token，页面内容片段:")
            lines = response.text.split('\n')
            for line_num, line in enumerate(lines):
                if 'token' in line.lower() or 't0ken' in line.lower():
                    print(f"行 {line_num}: {line.strip()[:200]}")
            
            print("🔍 尝试使用默认token...")
            # 如果实在找不到，尝试使用观察到的固定token
            default_token = "b8b6c49aToTA"
            print(f"⚠️ 使用默认token: {default_token}")
            return default_token
                
        except Exception as e:
            print(f"❌ 获取token失败: {e}")
            # fallback到默认token
            default_token = "b8b6c49aToTA"
            print(f"⚠️ 异常情况下使用默认token: {default_token}")
            return default_token
    
    def _submit_url(self, url: str, token: str) -> Optional[Dict]:
        """提交URL到DLPanda"""
        try:
            print(f"📤 提交URL到DLPanda: {url}")
            print(f"🔑 使用token: {token}")
            
            # 准备POST数据
            data = {
                'url': url,
                't0ken': token
            }
            
            # 添加更多headers模拟真实浏览器
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': self.base_url,
                'X-Requested-With': 'XMLHttpRequest'
            }
            
            print("📤 发送GET请求（表单使用GET方法）...")
            # DLPanda使用GET方法提交表单
            response = self.session.get(
                self.base_url,
                params=data,  # 使用params而不是data
                timeout=30,
                allow_redirects=True
            )
            
            print(f"📄 响应状态: {response.status_code}")
            print(f"📄 最终URL: {response.url}")
            print(f"📄 响应长度: {len(response.text)}")
            
            if response.status_code != 200:
                print(f"❌ 请求失败，状态码: {response.status_code}")
                print(f"响应内容前500字符: {response.text[:500]}")
                return None
            
            # 检查是否有下载链接
            print("🔍 查找下载链接...")
            download_links = self._extract_download_links(response.text)
            if download_links:
                print(f"✅ 找到 {len(download_links)} 个下载链接")
                return {
                    'html': response.text,
                    'download_links': download_links,
                    'url': response.url
                }
            else:
                print("⚠️ 未找到直接下载链接，尝试检查是否有异步加载...")
            
            # 检查页面是否包含视频信息，可能需要等待JavaScript执行
            print("🔍 检查页面是否有处理结果...")
            
            # 不再重试HTTP请求，而是检查当前页面是否有有用信息
            # 检查是否页面有重定向或其他有用信息
            if 'download' in response.text.lower() or 'video' in response.text.lower():
                print("💡 页面包含视频相关内容，可能需要JavaScript处理")
                # 这里可以作为Selenium的触发条件
            
            # 尝试查找可能的API端点
            ajax_data = self._check_for_ajax_response(response.text, url, token)
            if ajax_data:
                return ajax_data
            
            # 如果还是没有找到，尝试使用selenium方法
            print("🔄 尝试使用Selenium模式...")
            selenium_result = self._try_selenium_method(url)
            if selenium_result:
                return selenium_result
            
            # 即使没有下载链接，也返回页面内容供进一步分析
            print("⚠️ 返回页面内容供分析...")
            return {
                'html': response.text,
                'download_links': [],
                'url': response.url
            }
            
        except Exception as e:
            print(f"❌ 提交URL失败: {e}")
            import traceback
            print(f"详细错误: {traceback.format_exc()}")
            return None
    
    def _check_for_ajax_response(self, html: str, original_url: str, token: str) -> Optional[Dict]:
        """检查是否有AJAX响应"""
        try:
            # 查找可能的AJAX端点
            ajax_patterns = [
                r'\.post\(["\']([^"\']*)["\']',
                r'url:\s*["\']([^"\']*)["\']',
                r'action=["\']([^"\']*)["\']'
            ]
            
            for pattern in ajax_patterns:
                matches = re.findall(pattern, html)
                for match in matches:
                    if 'download' in match.lower() or 'api' in match.lower():
                        ajax_url = urljoin(self.base_url, match)
                        print(f"🔍 尝试AJAX端点: {ajax_url}")
                        
                        # 尝试POST到这个端点
                        try:
                            ajax_response = self.session.post(
                                ajax_url,
                                data={'url': original_url, 't0ken': token},
                                timeout=15
                            )
                            if ajax_response.status_code == 200:
                                download_links = self._extract_download_links(ajax_response.text)
                                if download_links:
                                    return {
                                        'html': ajax_response.text,
                                        'download_links': download_links,
                                        'url': ajax_response.url
                                    }
                        except:
                            continue
            
            return None
            
        except Exception as e:
            print(f"⚠️ 检查AJAX响应失败: {e}")
            return None
    
    def _extract_download_links(self, html: str) -> list:
        """从HTML中提取下载链接"""
        download_links = []
        
        # 下载链接的各种模式
        patterns = [
            # 直接的视频链接
            r'href="([^"]*\.mp4[^"]*)"',
            r'href="([^"]*video[^"]*)"',
            r'href="([^"]*download[^"]*)"',
            # 按钮和链接
            r'<a[^>]*class="[^"]*download[^"]*"[^>]*href="([^"]*)"',
            r'<a[^>]*href="([^"]*)"[^>]*download',
            r'<button[^>]*data-url="([^"]*)"',
            r'<button[^>]*onclick="[^"]*\'([^\']*\.mp4[^\']*)\'"',
            # JSON格式
            r'"download_url":\s*"([^"]*)"',
            r'"video_url":\s*"([^"]*)"',
            r'"url":\s*"([^"]*\.mp4[^"]*)"',
            # Blob URL和JavaScript变量
            r'blob:([^"\'>\s]*)',
            r'createObjectURL\([^)]*\)',
            r'videoUrl\s*=\s*["\']([^"\']*)["\']',
            r'downloadUrl\s*=\s*["\']([^"\']*)["\']',
            # API响应格式
            r'"playAddr":\s*"([^"]*)"',
            r'"src":\s*"([^"]*\.mp4[^"]*)"',
            # 可能的重定向链接
            r'location\.href\s*=\s*["\']([^"\']*)["\']',
            r'window\.open\(["\']([^"\']*)["\']',
            # TikTok特殊格式
            r'https://[^"\'>\s]*tiktok[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'https://[^"\'>\s]*douyin[^"\'>\s]*\.mp4[^"\'>\s]*',
            r'https://[^"\'>\s]*aweme[^"\'>\s]*\.mp4[^"\'>\s]*',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if match and (match.startswith('http') or match.startswith('//')):
                    # 处理相对URL
                    if match.startswith('//'):
                        match = 'https:' + match
                    elif match.startswith('/'):
                        match = urljoin(self.base_url, match)
                    
                    if match not in download_links:
                        download_links.append(match)
                        print(f"🔗 发现下载链接: {match[:80]}...")
        
        return download_links
    
    def _parse_video_data(self, video_data: Dict, original_url: str) -> Dict[str, Any]:
        """解析视频数据"""
        html = video_data.get('html', '')
        download_links = video_data.get('download_links', [])
        
        # 提取视频ID
        video_id_match = re.search(r'/video/(\d+)', original_url)
        video_id = video_id_match.group(1) if video_id_match else "unknown"
        
        # 基本视频信息结构
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
        
        # 设置下载链接
        if download_links:
            # 优先使用第一个链接作为主要下载链接
            video_info['video']['play_url'] = download_links[0]
            video_info['video']['play_url_no_watermark'] = download_links[0]
            
            # 如果有多个链接，可以存储备用链接
            if len(download_links) > 1:
                video_info['video']['alternative_urls'] = download_links[1:]
            
            print(f"✅ DLPanda成功获取到下载链接")
        else:
            # 如果没有直接下载链接，标记为需要其他方法处理
            print("⚠️ DLPanda未获取到直接下载链接，标记为信息不完整")
            video_info['video']['play_url'] = ''  # 空字符串表示需要其他方法
            video_info['video']['page_url'] = video_data.get('url', original_url)
            video_info['_dlpanda_incomplete'] = True  # 标记为不完整
        
        # 尝试从HTML中提取标题和其他信息
        self._extract_metadata_from_html(html, video_info)
        
        return video_info
    
    def _extract_metadata_from_html(self, html: str, video_info: Dict):
        """从HTML中提取元数据"""
        try:
            # 提取标题
            title_patterns = [
                r'<title>([^<]+)</title>',
                r'<h1[^>]*>([^<]+)</h1>',
                r'<h2[^>]*>([^<]+)</h2>',
                r'"title":"([^"]*)"',
                r'video-title[^>]*>([^<]+)<',
            ]
            
            for pattern in title_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    if title and 'dlpanda' not in title.lower() and len(title) > 5:
                        video_info['desc'] = title
                        print(f"📝 提取到标题: {title}")
                        break
            
            # 提取封面图片
            cover_patterns = [
                r'<img[^>]*src="([^"]*)"[^>]*video',
                r'<img[^>]*video[^>]*src="([^"]*)"',
                r'"cover":"([^"]*)"',
                r'"thumbnail":"([^"]*)"',
            ]
            
            for pattern in cover_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    cover_url = match.group(1)
                    if cover_url.startswith('http') or cover_url.startswith('//'):
                        if cover_url.startswith('//'):
                            cover_url = 'https:' + cover_url
                        video_info['video']['cover_url'] = cover_url
                        print(f"🖼️ 提取到封面: {cover_url[:80]}...")
                        break
            
        except Exception as e:
            print(f"⚠️ 提取元数据失败: {e}")
    
    def _try_selenium_method(self, url: str) -> Optional[Dict]:
        """使用Selenium在DLPanda网站上获取下载链接"""
        try:
            print("🚀 启动Selenium浏览器访问DLPanda...")
            
            # 检查selenium是否可用
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                import time
            except ImportError:
                print("❌ Selenium不可用，跳过此方法")
                return None
            
            # 配置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 无头模式
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # 启动浏览器
            driver = webdriver.Chrome(options=chrome_options)
            
            try:
                print("🌐 访问DLPanda网站...")
                driver.get(self.base_url)
                time.sleep(2)
                
                # 找到输入框并输入URL
                print("📝 输入视频URL...")
                url_input = driver.find_element(By.ID, "url")
                url_input.clear()
                url_input.send_keys(url)
                
                # 点击下载按钮
                print("🔽 点击下载按钮...")
                download_btn = driver.find_element(By.CSS_SELECTOR, ".one-click")
                download_btn.click()
                
                # 等待页面加载和处理
                print("⏳ 等待处理结果...")
                time.sleep(10)  # 等待JavaScript执行和异步请求
                
                # 检查新的页面内容
                new_html = driver.page_source
                download_links = self._extract_download_links(new_html)
                
                if download_links:
                    print(f"✅ Selenium方法找到 {len(download_links)} 个下载链接")
                    return {
                        'html': new_html,
                        'download_links': download_links,
                        'url': driver.current_url
                    }
                else:
                    # 再等待一段时间
                    print("⏳ 继续等待...")
                    time.sleep(5)
                    new_html = driver.page_source
                    download_links = self._extract_download_links(new_html)
                    
                    if download_links:
                        print(f"✅ Selenium方法(二次检查)找到 {len(download_links)} 个下载链接")
                        return {
                            'html': new_html,
                            'download_links': download_links,
                            'url': driver.current_url
                        }
                
                print("❌ Selenium方法未找到下载链接")
                return None
                
            finally:
                driver.quit()
                
        except Exception as e:
            print(f"❌ Selenium方法失败: {e}")
            return None
    
    def is_available(self) -> bool:
        """检查DLPanda服务是否可用"""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def test_connection(self) -> bool:
        """测试连接"""
        try:
            print("🔍 测试DLPanda连接...")
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                print("✅ DLPanda连接成功")
                return True
            else:
                print(f"❌ DLPanda连接失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ DLPanda连接异常: {e}")
            return False
# -*- coding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Copyright (c) 2024 by Hmily, All Rights Reserved.
"""

import os
import re
import subprocess
import sys
import platform
import zipfile
from pathlib import Path
import requests
from tqdm import tqdm
try:
    from live_recorder.logger import logger
except ImportError:
    # 如果没有logger模块，使用简单的print作为日志
    class SimpleLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
    logger = SimpleLogger()

current_platform = platform.system()
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
current_env_path = os.environ.get('PATH')
ffmpeg_path = os.path.join(execute_dir, 'ffmpeg')


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    """
    解压zip文件并智能处理ffmpeg目录结构
    """
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    temp_extract = os.path.join(extract_to, '_temp_ffmpeg_extract')

    # 先解压到临时目录
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_extract)

    # 查找ffmpeg可执行文件
    ffmpeg_bin_path = None
    for root, dirs, files in os.walk(temp_extract):
        if 'ffmpeg.exe' in files or 'ffmpeg' in files:
            ffmpeg_bin_path = root
            break

    # 移动ffmpeg文件到目标目录
    if ffmpeg_bin_path:
        target_ffmpeg_dir = os.path.join(extract_to, 'ffmpeg')
        if not os.path.exists(target_ffmpeg_dir):
            os.makedirs(target_ffmpeg_dir)

        # 复制所有文件
        for item in os.listdir(ffmpeg_bin_path):
            src = os.path.join(ffmpeg_bin_path, item)
            dst = os.path.join(target_ffmpeg_dir, item)
            if os.path.isfile(src):
                import shutil
                shutil.copy2(src, dst)
                logger.debug(f"Copied {item} to {target_ffmpeg_dir}")

    # 清理临时目录
    import shutil
    if os.path.exists(temp_extract):
        shutil.rmtree(temp_extract)

    # 删除zip文件
    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def get_lanzou_download_link(url: str, password: str | None = None) -> str | None:
    try:
        headers = {
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Origin': 'https://wweb.lanzouv.com',
            'Referer': 'https://wweb.lanzouv.com/iXncv0dly6mh',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
        }
        response = requests.get(url, headers=headers)
        sign = re.search("var skdklds = '(.*?)';", response.text).group(1)
        data = {
            'action': 'downprocess',
            'sign': sign,
            'p': password,
            'kd': '1',
        }
        response = requests.post('https://wweb.lanzouv.com/ajaxm.php', headers=headers, data=data)
        json_data = response.json()
        download_url = json_data['dom'] + "/file/" + str(json_data['url'])
        response = requests.get(download_url, headers=headers)
        return response.url
    except Exception as e:
        logger.error(f"Failed to obtain ffmpeg download address. {e}")


def get_github_ffmpeg_download_link():
    """
    从GitHub获取FFmpeg下载链接（备用方案）
    使用 BtbN/FFmpeg-Builds 项目的release
    """
    try:
        logger.info("尝试从GitHub获取FFmpeg下载链接...")
        # 使用固定版本的下载链接
        github_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        return github_url
    except Exception as e:
        logger.error(f"Failed to get GitHub ffmpeg link. {e}")
        return None


def get_gyan_ffmpeg_download_link():
    """
    从Gyan.dev获取FFmpeg下载链接（备用方案3）
    这是一个可靠的FFmpeg Windows构建源
    """
    try:
        logger.info("尝试从Gyan.dev获取FFmpeg下载链接...")
        # 使用essentials版本，文件较小
        gyan_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        return gyan_url
    except Exception as e:
        logger.error(f"Failed to get Gyan.dev ffmpeg link. {e}")
        return None


def install_ffmpeg_windows():
    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Installing the latest version of ffmpeg for Windows...")

        # 尝试多个下载源
        download_source = None
        ffmpeg_url = None

        # 方案1：从蓝奏云下载
        logger.info("尝试从蓝奏云下载...")
        try:
            ffmpeg_url = get_lanzou_download_link('https://wweb.lanzouv.com/iHAc22ly3r3g', 'eots')
            if ffmpeg_url:
                download_source = "lanzou"
                logger.info("✓ 蓝奏云下载链接获取成功")
        except Exception as e:
            logger.warning(f"蓝奏云下载失败: {e}")

        # 方案2：从Gyan.dev下载（更稳定）
        if not ffmpeg_url:
            logger.info("尝试从Gyan.dev下载...")
            try:
                ffmpeg_url = get_gyan_ffmpeg_download_link()
                if ffmpeg_url:
                    download_source = "gyan"
                    logger.info("✓ Gyan.dev下载链接获取成功")
            except Exception as e:
                logger.warning(f"Gyan.dev下载失败: {e}")

        # 方案3：从GitHub下载
        if not ffmpeg_url:
            logger.info("尝试从GitHub下载...")
            try:
                ffmpeg_url = get_github_ffmpeg_download_link()
                if ffmpeg_url:
                    download_source = "github"
                    logger.info("✓ GitHub下载链接获取成功")
            except Exception as e:
                logger.warning(f"GitHub下载失败: {e}")

        if ffmpeg_url:
            # 根据下载源确定文件名
            if download_source == "github":
                full_file_name = 'ffmpeg-master-latest-win64-gpl.zip'
                version = 'GitHub-latest'
            elif download_source == "gyan":
                full_file_name = 'ffmpeg-release-essentials.zip'
                version = 'Gyan-release'
            else:
                full_file_name = 'ffmpeg_latest_build_20250124.zip'
                version = 'v20250124'

            logger.info(f"准备下载FFmpeg - 源: {download_source}, 版本: {version}")
            logger.info(f"下载URL: {ffmpeg_url}")

            zip_file_path = Path(execute_dir) / full_file_name

            if Path(zip_file_path).exists():
                logger.info(f"发现已存在的安装文件: {zip_file_path}")
                logger.info("跳过下载，直接使用现有文件...")
            else:
                try:
                    logger.info(f"开始下载到: {zip_file_path}")
                    # 添加超时和错误处理
                    response = requests.get(ffmpeg_url, stream=True, timeout=60, allow_redirects=True)
                    response.raise_for_status()  # 检查HTTP错误

                    total_size = int(response.headers.get('Content-Length', 0))
                    logger.info(f"文件大小: {total_size / (1024*1024):.2f} MB")

                    if total_size == 0:
                        logger.warning("无法获取文件大小，继续下载...")

                    block_size = 8192  # 增加块大小提高下载速度
                    downloaded = 0

                    with open(zip_file_path, 'wb') as f:
                        if total_size > 0:
                            with tqdm(total=total_size, unit="B", unit_scale=True,
                                      ncols=100, desc=f'下载FFmpeg ({version})') as t:
                                for data in response.iter_content(block_size):
                                    if data:
                                        f.write(data)
                                        downloaded += len(data)
                                        t.update(len(data))
                        else:
                            # 如果无法获取文件大小，不显示进度条
                            for data in response.iter_content(block_size):
                                if data:
                                    f.write(data)
                                    downloaded += len(data)

                    logger.info(f"下载完成! 已下载: {downloaded / (1024*1024):.2f} MB")

                except requests.exceptions.RequestException as e:
                    logger.error(f"下载失败 - 网络错误: {e}")
                    if Path(zip_file_path).exists():
                        logger.info("清理不完整的下载文件...")
                        os.remove(zip_file_path)
                    return None
                except Exception as e:
                    logger.error(f"下载失败 - {type(e).__name__}: {e}")
                    if Path(zip_file_path).exists():
                        logger.info("清理不完整的下载文件...")
                        os.remove(zip_file_path)
                    return None

            # 解压文件
            try:
                logger.info(f"开始解压: {zip_file_path}")
                unzip_file(zip_file_path, execute_dir)
                logger.info("解压完成!")
            except Exception as e:
                logger.error(f"解压失败: {e}")
                return None

            # 设置环境变量
            os.environ['PATH'] = ffmpeg_path + os.pathsep + current_env_path

            # 获取ffmpeg.exe的完整路径
            ffmpeg_exe_path = os.path.join(ffmpeg_path, 'ffmpeg.exe')

            logger.info(f"检查FFmpeg路径: {ffmpeg_exe_path}")

            # 检查文件是否存在
            if not os.path.exists(ffmpeg_exe_path):
                logger.error(f"FFmpeg可执行文件不存在: {ffmpeg_exe_path}")
                # 尝试在ffmpeg目录中查找
                if os.path.exists(ffmpeg_path):
                    logger.info(f"ffmpeg目录内容: {os.listdir(ffmpeg_path)}")
                return None

            # 测试ffmpeg
            logger.info("测试FFmpeg...")
            result = subprocess.run([ffmpeg_exe_path, "-version"], capture_output=True, timeout=10)
            if result.returncode == 0:
                logger.info('✓ FFmpeg安装成功!')
                logger.info(f"FFmpeg版本: {result.stdout.decode()[:100]}")
                return ffmpeg_exe_path
            else:
                logger.error(f'FFmpeg测试失败: {result.stderr.decode()}')
                return None
        else:
            logger.error("所有下载源都失败了，请手动安装FFmpeg")
            logger.info("手动安装指南: 访问 https://www.gyan.dev/ffmpeg/builds/")
            return None

    except Exception as e:
        logger.error(f"安装FFmpeg时发生错误 - {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"详细错误:\n{traceback.format_exc()}")
        return None


def install_ffmpeg_mac():
    logger.warning("ffmpeg is not installed.")
    logger.debug("Installing the stable version of ffmpeg for macOS...")
    try:
        result = subprocess.run(["brew", "install", "ffmpeg"], capture_output=True)
        if result.returncode == 0:
            logger.debug('ffmpeg installation was successful. Restart for changes to take effect.')
            # 通常brew安装在/usr/local/bin或/opt/homebrew/bin
            import shutil
            ffmpeg_path = shutil.which('ffmpeg')
            return ffmpeg_path if ffmpeg_path else '/usr/local/bin/ffmpeg'
        else:
            logger.error("ffmpeg installation failed")
            return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install ffmpeg using Homebrew. {e}")
        logger.error("Please install ffmpeg manually or check your Homebrew installation.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        return None


def install_ffmpeg_linux():
    is_RHS = True

    try:
        logger.warning("ffmpeg is not installed.")
        logger.debug("Trying to install the stable version of ffmpeg")
        result = subprocess.run(['yum', '-y', 'update'], capture_output=True)
        if result.returncode != 0:
            logger.error("Failed to update package lists using yum.")
            return None

        result = subprocess.run(['yum', 'install', '-y', 'ffmpeg'], capture_output=True)
        if result.returncode == 0:
            logger.debug("ffmpeg installation was successful using yum. Restart for changes to take effect.")
            # 返回系统路径
            import shutil
            ffmpeg_path = shutil.which('ffmpeg')
            return ffmpeg_path if ffmpeg_path else '/usr/bin/ffmpeg'
        logger.error(result.stderr.decode('utf-8').strip())
    except FileNotFoundError:
        logger.debug("yum command not found, trying to install using apt...")
        is_RHS = False
    except Exception as e:
        logger.error(f"An error occurred while trying to install ffmpeg using yum: {e}")

    if not is_RHS:
        try:
            logger.debug("Trying to install the stable version of ffmpeg for Linux using apt...")
            result = subprocess.run(['apt', 'update'], capture_output=True)
            if result.returncode != 0:
                logger.error("Failed to update package lists using apt")
                return None

            result = subprocess.run(['apt', 'install', '-y', 'ffmpeg'], capture_output=True)
            if result.returncode == 0:
                logger.debug("ffmpeg installation was successful using apt. Restart for changes to take effect.")
                # 返回系统路径
                import shutil
                ffmpeg_path = shutil.which('ffmpeg')
                return ffmpeg_path if ffmpeg_path else '/usr/bin/ffmpeg'
            else:
                logger.error(result.stderr.decode('utf-8').strip())
        except FileNotFoundError:
            logger.error("apt command not found, unable to install ffmpeg. Please manually install ffmpeg by yourself")
        except Exception as e:
            logger.error(f"An error occurred while trying to install ffmpeg using apt: {e}")
    logger.error("Manual installation of ffmpeg is required. Please manually install ffmpeg by yourself.")
    return None


def install_ffmpeg():
    """
    安装ffmpeg

    Returns:
        成功返回ffmpeg路径，失败返回None
    """
    if current_platform == "Windows":
        return install_ffmpeg_windows()
    elif current_platform == "Linux":
        return install_ffmpeg_linux()
    elif current_platform == "Darwin":
        return install_ffmpeg_mac()
    else:
        logger.debug(f"ffmpeg auto installation is not supported on this platform: {current_platform}. "
                     f"Please install ffmpeg manually.")
    return None


def ensure_ffmpeg_installed(func):
    def wrapper(*args, **kwargs):
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
            version = result.stdout.strip()
            if result.returncode == 0 and version:
                return func(*args, **kwargs)
        except FileNotFoundError:
            pass
        return False

    def wrapped_func(*args, **kwargs):
        if sys.version_info >= (3, 7):
            res = wrapper(*args, **kwargs)
        else:
            res = wrapper(*args, **kwargs)
        if not res:
            install_ffmpeg()
            res = wrapper(*args, **kwargs)

        if not res:
            raise RuntimeError("ffmpeg is not installed.")

        return func(*args, **kwargs)

    return wrapped_func


def check_ffmpeg_installed() -> bool:
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
        version = result.stdout.strip()
        if result.returncode == 0 and version:
            return True
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"OSError occurred: {e}. ffmpeg may not be installed correctly or is not available in the system PATH.")
        print("Please delete the ffmpeg and try to download and install again.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return False


def check_ffmpeg() -> bool:
    if not check_ffmpeg_installed():
        return install_ffmpeg()
    return True

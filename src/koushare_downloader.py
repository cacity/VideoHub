#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
koushare.com 视频下载器
支持下载 https://www.koushare.com/live/details/{liveId}?vid={videoId} 格式的视频
"""

import hashlib
import time
import re
import os
import subprocess
import shutil
from urllib.parse import urlparse, parse_qs

import requests


# ============================================================
# ks-sign 签名算法（从 JS 源码逆向）
# ============================================================

SALT_KEY = "arfw2r4k4rdwrlmchvcu7q61fs"


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def generate_ks_sign(params: dict, method: str) -> tuple:
    """
    生成 ks-sign 和 ks-timestamp 头部
    算法：MD5(sorted_params & method=METHOD & timestamp=TS & saltmd5=SALT_MD5)
    """
    METHOD = method.upper()
    timestamp = int(time.time() * 1000)

    # 过滤空值
    filtered = {k: v for k, v in (params or {}).items()
                if v is not None and v != ""}

    # 按键名排序
    sorted_keys = sorted(filtered.keys())

    # 构建参数字符串
    parts = []
    for k in sorted_keys:
        v = filtered[k]
        if isinstance(v, bool):
            # JS: false/true（小写），Python 默认 False/True（大写），必须转换
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, (list, dict)):
            import json
            parts.append(f"{k}={json.dumps(v, separators=(',', ':'))}")
        else:
            parts.append(f"{k}={v}")
    param_str = "&".join(parts)

    salt_md5 = md5(SALT_KEY)
    suffix = f"method={METHOD}&timestamp={timestamp}&saltmd5={salt_md5}"
    message = f"{param_str}&{suffix}" if param_str else suffix

    sign = md5(message)
    return sign, timestamp


# ============================================================
# API 请求
# ============================================================

API_BASE = "https://api-core.koushare.com"

_SESSION = None
_ACCESS_TOKEN = ""


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.koushare.com/",
            "Origin": "https://www.koushare.com",
            "client": "front_web",
            "Content-Type": "application/json",
        })
    return _SESSION


def set_token(access_token: str):
    """直接设置 access token（从外部传入已有 token）"""
    global _ACCESS_TOKEN
    _ACCESS_TOKEN = access_token
    sess = _get_session()
    if access_token:
        sess.headers["Authorization"] = access_token
    else:
        sess.headers.pop("Authorization", None)


def login(username: str, password: str, area_code: str = "86") -> dict:
    """
    账号密码登录蔻享学术
    :param username: 手机号或邮箱
    :param password: 密码
    :param area_code: 手机区号，默认 86（中国大陆）
    :return: {"success": bool, "access_token": str, "user": dict, "error": str}
    """
    global _ACCESS_TOKEN
    url = f"{API_BASE}/iam/userLogin/accountLogin"
    body = {
        "flag": False,
        "password": password,
        "username": username,
        "areaCode": area_code,
    }
    headers = _signed_headers(body, "post")
    try:
        resp = _get_session().post(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return {"success": False, "error": data.get("msg", "登录失败")}

        token_data = data.get("data") or {}
        access_token = token_data.get("access_token", "")
        set_token(access_token)
        return {
            "success": True,
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token", ""),
            "user": token_data.get("user") or {},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _signed_headers(params: dict, method: str) -> dict:
    sign, ts = generate_ks_sign(params, method)
    return {
        "ks-sign": sign,
        "ks-timestamp": str(ts),
    }


def get_live_info(live_id: str) -> dict:
    """获取直播间基本信息（标题等）"""
    url = f"{API_BASE}/live/v2/live/{live_id}"
    params = {}
    headers = _signed_headers(params, "get")
    resp = _get_session().get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success") and str(data.get("code", ""))[:3] != "200":
        raise RuntimeError(f"获取直播信息失败: {data}")
    return data.get("data", {})


def get_video_info(live_id: str, video_id: str) -> dict:
    """
    从 /live/v1/user/livePlayback/list 获取分集信息（title、addr 直链等）。
    返回匹配 videoId 的条目，失败时返回 {}。
    """
    params = {"liveId": int(live_id), "pageNum": 1, "pageSize": 200}
    headers = _signed_headers(params, "get")
    try:
        resp = _get_session().get(
            f"{API_BASE}/live/v1/user/livePlayback/list",
            params=params, headers=headers, timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json().get("data") or []
            if isinstance(items, list):
                for item in items:
                    if str(item.get("videoId", "")) == str(video_id):
                        return item
    except Exception as e:
        print(f"      [警告] livePlayback/list 失败: {e}")
    return {}


def get_playback_url(live_id: str, video_id: str) -> dict:
    """
    获取回放视频 m3u8 地址
    POST /live/v2/live/playback/{liveId}?videoId={videoId}
    """
    url = f"{API_BASE}/live/v2/live/playback/{live_id}"
    query_params = {"videoId": video_id}
    sign_params = {"videoId": video_id}
    headers = _signed_headers(sign_params, "post")

    sess = _get_session()
    has_auth = bool(sess.headers.get("Authorization"))
    print(f"      [鉴权] Authorization header {'已设置' if has_auth else '未设置（未登录）'}")

    resp = sess.post(url, params=query_params, json={}, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success") and str(data.get("code", ""))[:3] != "200":
        raise RuntimeError(f"获取播放地址失败: {data}")
    return data.get("data", {})


# ============================================================
# URL 解析
# ============================================================

def parse_koushare_url(url: str) -> tuple:
    """
    从页面 URL 提取 liveId 和 videoId
    例如: https://www.koushare.com/live/details/44288?vid=183306
    """
    parsed = urlparse(url)
    m = re.search(r"/live/details/(\d+)", parsed.path)
    if not m:
        m2 = re.search(r"/video/videodetail/(\d+)", parsed.path)
        if m2:
            return None, m2.group(1)
        raise ValueError(f"无法从 URL 解析 liveId: {url}")
    live_id = m.group(1)

    qs = parse_qs(parsed.query)
    video_id = (qs.get("vid") or qs.get("videoId") or [None])[0]
    if not video_id:
        raise ValueError(f"无法从 URL 解析 videoId (vid=): {url}")

    return live_id, video_id


def is_koushare_url(url: str) -> bool:
    """判断 URL 是否为寇享视频链接"""
    return "koushare.com" in url


# ============================================================
# 质量选择
# ============================================================

def select_quality(playback_data: dict, quality: str = "FHD") -> str:
    """
    从播放数据中选择指定画质的 m3u8 地址。
    字段优先级：fileUrl > preUrl（需含 .m3u8）> url > playUrl
    quality: FHD (1080p), HD (720p), SD (480p)
    """
    quality = quality.upper()

    def _pick_url(item: dict) -> str:
        """返回第一个完整的 m3u8 URL（必须包含 .m3u8）"""
        for key in ("fileUrl", "preUrl", "url", "playUrl"):
            val = item.get(key) or ""
            if ".m3u8" in val:
                return val
        return ""

    for url_group in (playback_data.get("playbackUrls") or []):
        item_list = url_group.get("list") or []

        # ── 诊断：打印所有可用画质及其 URL 状态 ──────────────────────
        print(f"      [画质列表] 共 {len(item_list)} 个画质选项:")
        for item in item_list:
            label = item.get("labelEn", "?")
            h = item.get("height", "?")
            file_url = item.get("fileUrl") or ""
            pre_url = item.get("preUrl") or ""
            has_file = ".m3u8" in file_url
            has_pre = ".m3u8" in pre_url
            login_px = item.get("appLoginPx", 0)
            print(f"        {label}({h}p): fileUrl={'有' if has_file else '空'}, "
                  f"preUrl={'有m3u8' if has_pre else '无m3u8'}, "
                  f"loginPx={login_px}")

        # ── 优先选目标画质 ────────────────────────────────────────────
        for item in item_list:
            if (item.get("labelEn") or "").upper() == quality:
                url = _pick_url(item)
                if url:
                    print(f"      [选择] {quality} 画质 URL 已找到")
                    return url
                else:
                    login_px = item.get("appLoginPx", 0)
                    has_auth = bool(_get_session().headers.get("Authorization"))
                    if login_px and not has_auth:
                        print(f"      [提示] {quality} 需要登录才能获取 URL（appLoginPx={login_px}），请先在设置中登录蔻享账号")
                    else:
                        print(f"      [警告] {quality} URL 为空（fileUrl/preUrl 均无 .m3u8），将尝试回退")
                break

        # ── 按画质顺序回退 ────────────────────────────────────────────
        for q in ("FHD", "HD", "SD"):
            for item in item_list:
                url = _pick_url(item)
                if url and (item.get("labelEn") or "").upper() == q:
                    print(f"      [回退] {quality} 不可用，改用 {q}（{item.get('height', '?')}p）")
                    return url

    url = playback_data.get("url") or playback_data.get("playUrl")
    if url:
        return url

    raise RuntimeError(f"播放数据中未找到可用的视频地址，数据:\n{playback_data}")


# ============================================================
# 下载
# ============================================================

def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _get_ffmpeg_executable() -> str:
    """获取 ffmpeg 可执行文件路径，优先使用 VideoHub 本地 ffmpeg"""
    try:
        from ffmpeg_install import ffmpeg_path as local_ffmpeg_dir
        local_exe = os.path.join(local_ffmpeg_dir, "ffmpeg.exe")
        if os.path.exists(local_exe):
            return local_exe
    except Exception:
        pass
    # 回退到系统 PATH
    found = shutil.which("ffmpeg")
    return found if found else "ffmpeg"


def _parse_m3u8(m3u8_url: str) -> tuple:
    """
    下载并解析 m3u8 文件，返回 (total_segments, total_duration_seconds)
    遇到 master playlist 会自动跟进第一个 variant stream。
    """
    headers = {
        "Referer": "https://www.koushare.com/",
        "Origin": "https://www.koushare.com",
    }
    resp = requests.get(m3u8_url, headers=headers, timeout=15)
    resp.raise_for_status()
    text = resp.text

    # master playlist：找第一个非注释、非空行的 URI
    if "#EXT-X-STREAM-INF" in text:
        from urllib.parse import urljoin
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                text = requests.get(urljoin(m3u8_url, line), headers=headers, timeout=15).text
                break

    total_segments = 0
    total_duration = 0.0
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF:"):
            try:
                total_duration += float(line.split(":")[1].rstrip(","))
            except ValueError:
                pass
            total_segments += 1

    return total_segments, total_duration


def download_with_ffmpeg(m3u8_url: str, output_path: str, progress_callback=None):
    """使用 ffmpeg 下载并合并 HLS 流，通过 -progress 实时报告进度"""
    ffmpeg_exe = _get_ffmpeg_executable()
    print(f"[ffmpeg] 开始下载: {output_path}")

    # 先解析 m3u8 获取总时长，用于计算进度百分比（仅对 HLS 有效）
    total_segments = 0
    total_duration = 0.0
    if ".m3u8" in m3u8_url:
        if progress_callback:
            progress_callback("正在解析视频分片信息...", 28)
        try:
            total_segments, total_duration = _parse_m3u8(m3u8_url)
            if total_segments and progress_callback:
                progress_callback(
                    f"共 {total_segments} 个分片，总时长 {int(total_duration//60)}m{int(total_duration%60)}s，开始下载...",
                    30,
                )
        except Exception as e:
            print(f"[警告] 解析 m3u8 失败，将无法显示精确进度: {e}")
            if progress_callback:
                progress_callback("正在下载视频流...", 30)
    else:
        if progress_callback:
            progress_callback("正在下载视频流...", 30)

    cmd = [
        ffmpeg_exe, "-y",
        "-headers", "Referer: https://www.koushare.com/\r\nOrigin: https://www.koushare.com\r\n",
        "-i", m3u8_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,  # 丢弃 stderr，避免管道缓冲区撑满导致死锁
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # ffmpeg -progress 每隔约 0.5s 输出一组 key=value，以 progress=... 结尾
    out_time_us = 0  # microseconds
    for line in proc.stdout:
        line = line.strip()
        if line.startswith("out_time_us="):
            try:
                out_time_us = int(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("progress=") and progress_callback and total_duration > 0:
            elapsed_sec = out_time_us / 1_000_000
            pct = int(30 + min(elapsed_sec / total_duration, 1.0) * 67)  # 30~97%
            elapsed_str = f"{int(elapsed_sec//60)}m{int(elapsed_sec%60)}s"
            total_str = f"{int(total_duration//60)}m{int(total_duration%60)}s"
            progress_callback(
                f"下载中 {elapsed_str} / {total_str}（{pct}%）",
                pct,
            )

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 下载失败（returncode={proc.returncode}），请检查网络或 URL 是否有效")

    print(f"[完成] 已保存到: {output_path}")
    if progress_callback:
        progress_callback("下载完成", 100)


# ============================================================
# 主下载入口
# ============================================================

def download(url: str, output_dir: str = ".", quality: str = "FHD",
             progress_callback=None) -> dict:
    """
    下载寇享视频
    :param url: 寇享视频页面 URL
    :param output_dir: 输出目录
    :param quality: 画质 FHD/HD/SD（仅在 HLS 回退时有效）
    :param progress_callback: 进度回调 (message, percent)
    :return: {"success": bool, "file_path": str, "title": str, "error": str}
    """
    try:
        print(f"[1/3] 解析 URL: {url}")
        if progress_callback:
            progress_callback("正在解析 URL...", 5)

        live_id, video_id = parse_koushare_url(url)
        print(f"      liveId={live_id}, videoId={video_id}")

        title = f"koushare_{live_id}_{video_id}"

        # ── 步骤 2：从播放列表接口获取标题 ────────────────────────────
        print("[2/3] 获取视频信息...")
        if progress_callback:
            progress_callback("正在获取视频信息...", 15)

        if live_id:
            video_item = get_video_info(live_id, video_id)
            if video_item:
                raw_title = video_item.get("title") or video_item.get("name")
                if raw_title:
                    title = sanitize_filename(raw_title)
                    print(f"      分集标题: {title}")

            # 兜底：用直播间/系列名称
            if title == f"koushare_{live_id}_{video_id}":
                try:
                    info = get_live_info(live_id)
                    raw_title = info.get("title") or info.get("name") or title
                    title = sanitize_filename(raw_title)
                    print(f"      系列标题（兜底）: {title}")
                except Exception as e:
                    print(f"      [警告] 获取系列标题失败: {e}")

        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{title}.mp4")

        # ── 步骤 3：下载 ───────────────────────────────────────────────
        # 始终通过 get_playback_url 拿有效的 HLS 地址（addr 直链需要额外鉴权，不可用）
        print(f"[3/3] 获取 {quality} 画质播放地址...")
        has_auth = bool(_get_session().headers.get("Authorization"))
        if quality == "FHD" and not has_auth:
            print("      [提示] 请求 FHD 画质但尚未登录，FHD 可能需要登录才可用（请在设置中登录蔻享账号）")
        if progress_callback:
            progress_callback("正在获取播放地址...", 25)
        playback_data = get_playback_url(live_id, video_id)
        m3u8_url = select_quality(playback_data, quality)
        print(f"      m3u8: {m3u8_url[:80]}...")
        if progress_callback:
            progress_callback(f"正在下载: {title}", 30)
        download_with_ffmpeg(m3u8_url, output_path, progress_callback)

        return {"success": True, "file_path": output_path, "title": title}

    except Exception as e:
        print(f"[错误] 寇享视频下载失败: {e}")
        return {"success": False, "error": str(e)}

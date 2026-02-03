import re
from datetime import datetime
from typing import Optional, List, Dict, Any
import requests


class DouyinVideoInfo:
    def __init__(self):
        self.aweme_id: Optional[str] = None
        self.comment_count: Optional[int] = None
        self.digg_count: Optional[int] = None
        self.share_count: Optional[int] = None
        self.collect_count: Optional[int] = None
        self.nickname: Optional[str] = None
        self.signature: Optional[str] = None
        self.desc: Optional[str] = None
        self.create_time: Optional[str] = None
        self.video_url: Optional[str] = None
        self.type: Optional[str] = None
        self.image_url_list: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "aweme_id": self.aweme_id,
            "comment_count": self.comment_count,
            "digg_count": self.digg_count,
            "share_count": self.share_count,
            "collect_count": self.collect_count,
            "nickname": self.nickname,
            "signature": self.signature,
            "desc": self.desc,
            "create_time": self.create_time,
            "video_url": self.video_url,
            "type": self.type,
            "image_url_list": self.image_url_list,
        }


pattern = re.compile(r'"video":{"play_addr":{"uri":"([a-z0-9]+)"')
c_v_url = "https://www.iesdouyin.com/aweme/v1/play/?video_id=%s&ratio=1080p&line=0"

stats_regex = re.compile(r'"statistics"\s*:\s*\{([\s\S]*?)\},')
nickname_signature_regex = re.compile(r'"nickname":\s*"([^"]+)",\s*"signature":\s*"([^"]+)"')
ct_regex = re.compile(r'"create_time":\s*(\d+)')
desc_regex = re.compile(r'"desc":\s*"([^"]+)"')


def format_date(timestamp: int) -> str:
    date = datetime.fromtimestamp(timestamp)
    return date.strftime("%Y-%m-%d %H:%M:%S")


def do_get(url: str) -> requests.Response:
    import os
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36"
    }

    # 从环境变量读取代理配置
    proxy = os.getenv("PROXY")
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }

    resp = requests.get(url, headers=headers, proxies=proxies, timeout=30)
    return resp


def parse_img_list(body: str) -> List[str]:
    content = body.replace(r"\u002F", "/").replace("/", "/")
    
    img_regex = re.compile(r'{"uri":"[^\s"]+","url_list":\["(https://p\d{1,2}-sign\.douyinpic\.com/[^"]+)"')
    url_ret_regex = re.compile(r'"uri":"([^\s"]+)","url_list":')
    
    first_urls = img_regex.findall(content)
    
    url_list = url_ret_regex.findall(content)
    url_set = set(url_list)
    
    r_list = []
    for url_set_key in url_set:
        t = next((item for item in first_urls if url_set_key in item), None)
        if t:
            r_list.append(t)
    
    filtered_r_list = [url for url in r_list if "/obj/" not in url]
    
    print(f"filteredRList.length: {len(filtered_r_list)}")
    return filtered_r_list


def get_video_info(url: str) -> DouyinVideoInfo:
    video_type = "video"
    img_list: List[str] = []
    video_url = ""
    
    resp = do_get(url)
    body = resp.text
    
    match = pattern.search(body)
    if not match:
        video_type = "img"
    
    if video_type == "video":
        video_url = c_v_url % match.group(1)
    else:
        img_list = parse_img_list(body)
    
    au_match = nickname_signature_regex.search(body)
    ct_match = ct_regex.search(body)
    desc_match = desc_regex.search(body)
    stats_match = stats_regex.search(body)
    
    if not stats_match:
        raise Exception("No stats found in the response.")
    
    inner_content = stats_match.group(0)
    
    aweme_id_match = re.search(r'"aweme_id"\s*:\s*"([^"]+)"', inner_content)
    comment_count_match = re.search(r'"comment_count"\s*:\s*(\d+)', inner_content)
    digg_count_match = re.search(r'"digg_count"\s*:\s*(\d+)', inner_content)
    share_count_match = re.search(r'"share_count"\s*:\s*(\d+)', inner_content)
    collect_count_match = re.search(r'"collect_count"\s*:\s*(\d+)', inner_content)
    
    douyin_video_info = DouyinVideoInfo()
    douyin_video_info.aweme_id = aweme_id_match.group(1) if aweme_id_match else None
    douyin_video_info.comment_count = int(comment_count_match.group(1)) if comment_count_match else None
    douyin_video_info.digg_count = int(digg_count_match.group(1)) if digg_count_match else None
    douyin_video_info.share_count = int(share_count_match.group(1)) if share_count_match else None
    douyin_video_info.collect_count = int(collect_count_match.group(1)) if collect_count_match else None
    douyin_video_info.video_url = video_url
    douyin_video_info.type = video_type
    douyin_video_info.image_url_list = img_list
    
    if au_match:
        douyin_video_info.nickname = au_match.group(1)
        douyin_video_info.signature = au_match.group(2)
    
    if ct_match:
        timestamp = int(ct_match.group(1))
        douyin_video_info.create_time = format_date(timestamp)
    
    if desc_match:
        douyin_video_info.desc = desc_match.group(1)
    
    print(douyin_video_info.to_dict())
    return douyin_video_info


def get_video_id(url: str) -> str:
    resp = do_get(url)
    body = resp.text
    match = pattern.search(body)
    if not match:
        raise Exception("Video ID not found in URL")
    return match.group(1)


def get_video_url(url: str) -> str:
    video_id = get_video_id(url)
    download_url = c_v_url % video_id
    return download_url
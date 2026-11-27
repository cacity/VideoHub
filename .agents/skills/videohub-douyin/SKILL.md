---
name: videohub-douyin
description: 下载抖音视频、整组图集或用户主页作品，复用 src/douyin_cli.py。适合分享文本、短链接、视频/图文链接和主页链接。
allowed-tools: Bash(python src/douyin_cli.py*)
---

# VideoHub Douyin Download

复用 `F:/work/VideoHub/src/douyin_cli.py`。

## 适用场景
- 下载单个抖音视频
- 下载图文作品中的整组图片，保留顺序与真实图片格式
- 下载用户主页作品
- 处理分享文本中的抖音链接
- 指定下载目录

## 常用命令
```bash
python src/douyin_cli.py "https://v.douyin.com/xxxxx/"
python src/douyin_cli.py "https://www.douyin.com/video/xxxxx" -o "workspace/douyin_downloads"
python src/douyin_cli.py "https://www.douyin.com/note/xxxxx" -o "workspace/douyin_downloads"
python src/douyin_cli.py "https://www.douyin.com/user/xxxxx" --cookie "your_cookie" --limit 3
```

## 前置条件
- 视频和图集依次使用 `f2` → DLPanda → HelloTik → PeanutDL，解析或媒体地址失败时有限回退。图集链接仅返回合成视频/封面的来源会跳过；短链接先识别是否为图文。不再需要本地 douyinVd 服务。
- `f2` 返回 HTTP 403 后，同一程序进程内相同 Cookie/代理/UA 配置暂停该来源15分钟，期间公开单视频直接走 DLPanda；到期或配置变更后再试，不表示已修好F2接口。查看带作品ID、实际来源与保存路径的阶段结果，不把“解析完成”当作文件已下载。
- 第三方仅用于公开作品回退，绝不能向其解析或媒体请求转发用户抖音 Cookie。HelloTik 和 PeanutDL 是网页内部协议，遇登录/点数/验证码/限流时停止该来源，不自动购买、破解验证或反复重试；网页改版可能需要适配。
- 图集保存到 `<标题_作品ID>_images/<来源>/`，按 `001.webp`、`002.jpg` 等实际格式编号；全部图片验证可解码后写入 `gallery.json`，记录应保存/已保存数量。图片请求失败先试该图备用地址，再有限切换来源；切换须作品ID、类型和图片数量一致，缺图不得报告完成。重复下载验证并复用已有图片。
- 图集无需视频转录/字幕，勾选转录选项时也保存图片到所选抖音目录。2026-11-27 用户样本7629442747300907001经PeanutDL完整保存10/10张WebP（长边3240px）；HelloTik首次媒体超时，随后默认链重试完整保存10/10张JPEG（横图1920×1280、竖图1440×2160）。DLPanda仅合成视频，F2为403；来源结果和清晰度按实际样本区分。
- 用户主页批量下载需要有效 Cookie 和可用的 `f2` 环境。
- 当前 CLI 默认保存视频和封面，不保存 JSON 元数据，不下载音乐。

## 注意
- 用户主页批量下载已有入口，但失败原因可能是 Cookie 缺失/失效、`f2` 缺失、主页不可访问或解析不到作品；不要在未实际运行前承诺一定可下载。
- 若用户给的是分享口令文本，先提取出 URL 再调用 CLI。

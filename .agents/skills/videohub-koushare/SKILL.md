---
name: videohub-koushare
description: 处理蔻享学术视频下载与登录态说明。复用现有 koushare_downloader 和 GUI 中的 token/login 流程，不重造认证逻辑。
---

# VideoHub Koushare

蔻享能力分为两部分：
- 下载逻辑：`F:/work/VideoHub/src/koushare_downloader.py`
- 登录 / token 持久化：`F:/work/VideoHub/main.py`

## 适用场景
- 用户给出 `koushare.com` 链接
- 需要说明如何登录或设置 token
- 需要解释为什么未登录时拿不到 FHD

## 当前约束
- `set_token()` 在 `F:/work/VideoHub/src/koushare_downloader.py:91`
- `login()` 在 `F:/work/VideoHub/src/koushare_downloader.py:102`
- FHD 通常依赖登录态
- `Authorization` 头直接使用 token，不是 `Bearer <token>`

## 推荐操作
- 优先引导用户通过 GUI 设置页完成账号登录或粘贴 token
- 下载流程继续复用项目现有 Koushare 处理链路
- 如果用户要排查鉴权问题，先检查 token 是否已设置，以及目标资源是否需要登录

## 注意
- 不要把 token 写进代码或提交到 git。
- 这个 skill 第一阶段以引导和正确路由为主，不单独重建一套 CLI 认证入口。

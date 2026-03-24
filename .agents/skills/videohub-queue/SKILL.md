---
name: videohub-queue
description: 管理 VideoHub 的闲时队列和本地 API。适用于 Chrome 插件、队列查看、添加任务、清空任务和调整闲时时间窗口。
allowed-tools: Bash(curl*)
---

# VideoHub Idle Queue

复用 `F:/work/VideoHub/src/api_server.py:19` 提供的本地 API。

## 前置条件
必须先启动 GUI：
```bash
python main.py
```
GUI 启动后会拉起本地 Flask API，默认端口 `8765`。

## 可用接口
- `GET /api/health`
- `GET /api/queue`
- `POST /api/queue/add`
- `DELETE /api/queue/clear`
- `DELETE /api/queue/remove/<task_id>`
- `GET /api/settings`
- `PUT /api/settings`

## 示例
```bash
curl http://127.0.0.1:8765/api/health
curl http://127.0.0.1:8765/api/queue
curl -X POST http://127.0.0.1:8765/api/queue/add -H "Content-Type: application/json" -d '{"platform":"youtube","url":"https://example.com","title":"sample"}'
curl -X DELETE http://127.0.0.1:8765/api/queue/remove/0
curl -X DELETE http://127.0.0.1:8765/api/queue/clear
```

## 请求要求
新增任务至少包含：
- `platform`
- `url`
- `title`

## 注意
- 这个 skill 不是独立后端，它依赖正在运行的 GUI 状态。
- 队列实际执行仍由 `main.py` 中的 idle queue 定时逻辑负责。

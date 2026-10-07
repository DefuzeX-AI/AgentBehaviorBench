# Docker 开发指南

本项目提供开发模式 Docker 编排，包含：

- `backend`：FastAPI（`8000`）
- `frontend`：Vite Dev Server（`1420`）

## 1. 前置准备

1. 在项目根目录复制环境变量模板：

```bash
cp .env.example .env
```

2. 按需在 `.env` 中填写模型供应商 API Key（如 `OPENAI_API_KEY` 等）。

## 2. 启动

```bash
docker compose up --build
```

访问地址：

- 前端：http://127.0.0.1:1420
- 后端：http://127.0.0.1:8000

## 3. 停止

```bash
docker compose down
```

## 4. 日志

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

## 5. 数据持久化

默认已挂载以下目录（容器重启后保留）：

- `./.runtime/uploads`（上传文件与派生图片）
- `./.checkpoints`（工作流 checkpoint）
- `./.vectorstore`（检索索引）

## 6. 说明

- 该方案是**开发模式**，后端使用 `--reload`，前端为 Vite 热更新。
- 不包含 Tauri 桌面壳容器化，仅覆盖 Web 开发链路。

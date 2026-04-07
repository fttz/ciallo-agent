# Ciallo Agent

面向个人用户的智能聊天助手项目骨架，包含：

- Web 前端：Next.js + TypeScript
- 后端服务：FastAPI + Python
- 能力方向：多模型接入、流式聊天、图片与文件上传、文件解析（逐步完善）

## 当前阶段

已完成第一版工程初始化：

- 聊天页面骨架
- 模型列表接口
- 流式聊天接口（占位实现）
- 文件上传接口（占位实现）
- Docker Compose 本地编排

## 项目结构

```text
apps/
  web/       # Next.js 前端
  api/       # FastAPI 后端
docs/
  requirements.md
  technical-selection.md
infra/
  docker/
```

## 本地启动

1. 复制环境变量

```bash
cp .env.example .env
```

2. 使用 uv 初始化 Python 运行环境

```bash
uv sync
```

如果你在中国，建议优先使用清华 PyPI 镜像：

```bash
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple uv sync
```

如果看到 uv 关于 hardlink 的警告，可以一并指定：

```bash
UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple UV_LINK_MODE=copy uv sync
```

3. 启动后端

```bash
uv run --directory apps/api uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. 启动前端

```bash
cd apps/web && npm run dev
```

或在仓库根目录执行：

```bash
npm run dev:web
```

5. 一键关闭并重启前后端（推荐）

```bash
./scripts/restart_services.sh
```

清理本地运行缓存与日志：

```bash
npm run clean
```

脚本会自动：

- 关闭当前占用 `8000/3000` 端口的旧服务
- 重启 FastAPI 后端与 Next.js 前端
- 将 PID 与日志写入 `.run/`

6. 或使用 Docker 启动

```bash
docker compose up --build
```

7. 访问地址

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:8000/api/health

## 下一个里程碑建议

1. 接入真实模型网关（LiteLLM）
2. 落地数据库与会话持久化
3. 落地文件解析任务队列
4. 补齐鉴权与设置页

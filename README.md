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

2. 使用 Docker 启动

```bash
docker compose up --build
```

3. 访问地址

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:8000/api/health

## 下一个里程碑建议

1. 接入真实模型网关（LiteLLM）
2. 落地数据库与会话持久化
3. 落地文件解析任务队列
4. 补齐鉴权与设置页

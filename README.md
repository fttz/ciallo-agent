# Ciallo Agent

面向个人用户的智能聊天助手项目，包含：

- Web 前端：Next.js + TypeScript
- 后端服务：FastAPI + Python
- 能力方向：多模型接入、流式聊天、图片与文档上传、文件解析、会话管理与联网搜索

## 当前阶段

已完成可本地运行的聊天助手基础版：

- 前端聊天界面与后端 FastAPI 服务
- OpenAI 兼容模型网关与多模型列表
- SSE 流式聊天接口，支持停止生成、重新生成、思考内容展示
- 图片上传与视觉模型自动切换
- 文档上传、解析与上下文注入，支持 PDF、DOCX、TXT、MD、XLSX、CSV、PPTX、JSON 等格式问答
- 本地文件会话存储，支持新建、切换、重命名、删除
- Agent 工具调用基础能力，支持按需联网搜索
- 可视化设置页，支持配置模型网关、模型列表、搜索 API、搜索结果重排与 Agent 参数
- 本地一键启动脚本

## 项目结构

```text
apps/
  web/       # Next.js 前端
  api/       # FastAPI 后端
docs/
  requirements.md
  technical-selection.md
scripts/
  restart_services.sh
```

## 本地启动

1. 复制环境变量

```bash
cp .env.example .env
```

推荐在 `.env` 中配置模型 API Key：

```bash
MODEL_API_KEY=你的模型服务 API Key
```

如果没有提前配置，前端启动后会弹出窗口要求填写 `MODEL_API_KEY`。也可以在左侧栏底部的“设置”中配置模型、搜索 API 和 Agent 参数；保存后会写入 `.env` 并立即应用到当前后端进程。

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

6. 访问地址

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:8000/api/health

## 下一个里程碑建议

1. 继续扩展聊天流式生成、文件解析、会话管理的端到端测试覆盖
2. 增强设置页的密钥清除、配置导入导出与连接测试
3. 为生成中会话增加更明确的列表状态提示
4. 按需迁移会话存储到 SQLite 或 PostgreSQL

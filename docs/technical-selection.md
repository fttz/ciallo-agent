# 技术选型

## 1. 整体架构

- 前端：Next.js + TypeScript
- 后端：FastAPI + Python
- 模型接入：OpenAI 兼容协议，后端直连模型网关
- Agent 编排：LangGraph + LangChain OpenAI 兼容客户端
- 文件存储：本地目录
- 会话持久化：本地 JSON 文件
- 实时输出：SSE（Server-Sent Events）
- 部署方式：本地直接启动（uv + npm）

## 2. 前端

### 技术栈

- Next.js 15
- React 18
- TypeScript
- 全局 CSS（`apps/web/app/globals.css`）
- react-markdown + remark-gfm 渲染 AI 输出
- heic2any 处理 HEIC/HEIF 图片转码

### 选择原因

- Next.js 路由、SSR、中间层能力完整，适合做应用级产品
- TypeScript 保证消息结构和状态的可维护性
- 当前 UI 以单文件全局 CSS 维护，适合快速迭代本地单页应用
- react-markdown + remark-gfm 满足代码块、表格、列表等回答渲染需求

## 3. 后端

### 技术栈

- FastAPI
- Pydantic v2
- Uvicorn
- httpx
- LangChain + LangGraph
- pytest

### 选择原因

- FastAPI 对异步 IO、流式响应、文件上传、类型约束友好
- Python 在模型接入、文件解析、AI 工具链方面生态最成熟
- Pydantic 对消息协议和文件元数据建模效率高
- pytest 用于覆盖文件解析、会话持久化、流式生成、配置写入等关键路径

## 4. 模型接入

### 方案

- 统一使用 OpenAI 兼容协议
- 后端封装 Model Gateway，负责模型列表解析、默认模型选择和视觉模型路由
- 模型配置通过环境变量 / `.env` 管理（MODEL_CONFIGS），也可通过设置页写入
- 支持能力标签：text、vision、reasoning
- Agent 通过 LangGraph 绑定 web_search 工具，按需触发联网搜索

### 设计要点

- 前端不直接调用模型，所有请求走后端
- 后端根据消息内容（是否含图片）校验模型能力
- 统一错误映射，模型调用失败返回可读错误信息
- 缺少 MODEL_API_KEY 时，前端弹窗引导用户填写，后端同步更新当前运行时配置与 `.env`

## 5. 文件上传与存储

- 上传文件存储在本地目录（`./uploads`）
- 后端校验文件类型和大小
- 文件元数据保存在会话上下文中
- 无需对象存储，本地够用

## 6. 文件解析

### 解析库

| 文件类型 | 解析方案 |
|---------|---------|
| PDF | LangChain PyPDFLoader + pypdf |
| DOCX | docx2txt |
| DOC | UnstructuredWordDocumentLoader |
| PPT/PPTX | UnstructuredPowerPointLoader + python-pptx |
| XLSX/CSV | openpyxl + Python csv |
| TXT/MD | 原生读取 |
| JSON | 原生 json |
| HTML/HTM | BSHTMLLoader |
| URL 快捷文件 | WebBaseLoader |

### 架构

- 统一 Parser 接口，每种文件类型一个实现
- 解析同步执行（文件体积受限于 MAX_UPLOAD_MB，无需异步队列）
- 输出纯文本，直接注入对话上下文
- 超长文件截断处理（PARSER_MAX_CHARS 控制）
- XLSX/CSV 会转成 Markdown 表格，JSON 会格式化后注入上下文，便于模型阅读

## 7. 联网搜索

### 方案

- 后端判断用户问题是否需要搜索
- 调用搜索 API 获取结果
- 对结果进行 rerank 筛选
- 将高质量结果注入上下文辅助回答

### 当前实现

- 搜索源：百度搜索 API
- Rerank：阿里云 DashScope（gte-rerank-v2）
- 通过环境变量 / `.env` / 设置页控制开关和参数
- 工具调用过程通过 SSE 返回给前端，并随 assistant 消息持久化

## 8. 会话持久化

- 使用本地 JSON 文件存储会话和消息
- 路径通过 SESSION_STORE_PATH 配置
- assistant 消息会保存工具调用结果，用户消息会保存图片与文档上下文
- 生成任务在后端后台继续执行，前端刷新或断开连接后，完成结果仍会写入历史记录
- 后续可迁移到 SQLite 或 PostgreSQL，但当前阶段文件足够

## 9. 设置与配置

- 设置页位于左侧栏底部
- 支持配置模型网关、模型列表、默认模型、视觉模型、思考模式
- 支持配置联网搜索、搜索规划模型、搜索 Top K、抓取 Top K、搜索结果重排模型
- 支持配置 Agent 最大工具轮次和工具调用状态展示
- 设置保存后会写入 `.env` 并同步更新当前后端进程内配置

## 10. 测试策略

- 后端使用 pytest
- 前端当前使用 Next.js production build 作为类型与构建检查
- 根目录 `npm test` 串联后端测试、后端编译检查和前端构建检查
- 测试重点覆盖文件解析、会话持久化、工具调用保存、聊天流式接口、后台生成完成保存、停止生成和设置写入 `.env`

## 11. 项目结构

```text
apps/
  web/       # Next.js 前端
  api/       # FastAPI 后端
docs/        # 需求与技术文档
scripts/     # 启动与运维脚本
```

## 12. 关键设计决策

### 不用数据库

当前单用户、本地部署，JSON 文件持久化足够。引入数据库增加部署复杂度，收益不大。

### 不用异步队列

文件上传有大小限制（20MB），解析耗时可控，同步处理即可。不需要 Celery/Redis。

### 不做鉴权

单用户本地使用，不暴露公网。无需登录、JWT、权限体系。

### SSE 而非 WebSocket

聊天流式输出主要是服务端到客户端的单向事件流，SSE 实现简单，兼容性好。当前后端会把生成任务放入后台执行，前端断开后也不取消任务，避免刷新页面导致回答丢失。

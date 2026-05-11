# 技术选型

## 1. 整体架构

- 前端：Next.js + TypeScript
- 后端：FastAPI + Python
- 模型接入：OpenAI 兼容协议，通过 LiteLLM 或直连
- 文件存储：本地目录
- 会话持久化：本地 JSON 文件
- 实时输出：SSE（Server-Sent Events）
- 部署方式：本地直接启动（uv + npm）

## 2. 前端

### 技术栈

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS 4
- react-markdown + remark-gfm 渲染 AI 输出

### 选择原因

- Next.js 路由、SSR、中间层能力完整，适合做应用级产品
- TypeScript 保证消息结构和状态的可维护性
- Tailwind 开发效率高，样式一致性好

## 3. 后端

### 技术栈

- FastAPI
- Pydantic v2
- Uvicorn

### 选择原因

- FastAPI 对异步 IO、流式响应、文件上传、类型约束友好
- Python 在模型接入、文件解析、AI 工具链方面生态最成熟
- Pydantic 对消息协议和文件元数据建模效率高

## 4. 模型接入

### 方案

- 统一使用 OpenAI 兼容协议
- 后端封装 Model Gateway，屏蔽多供应商差异
- 模型配置通过环境变量管理（MODEL_CONFIGS）
- 支持能力标签：text、vision、reasoning

### 设计要点

- 前端不直接调用模型，所有请求走后端
- 后端根据消息内容（是否含图片）校验模型能力
- 统一错误映射，模型调用失败返回可读错误信息

## 5. 文件上传与存储

- 上传文件存储在本地目录（`./uploads`）
- 后端校验文件类型和大小
- 文件元数据保存在会话上下文中
- 无需对象存储，本地够用

## 6. 文件解析

### 解析库

| 文件类型 | 解析方案 |
|---------|---------|
| PDF | PyMuPDF |
| DOCX | python-docx |
| PPTX | python-pptx |
| XLSX/CSV | openpyxl + Python csv |
| TXT/MD | 原生读取 |
| JSON | 原生 json |

### 架构

- 统一 Parser 接口，每种文件类型一个实现
- 解析同步执行（文件体积受限于 MAX_UPLOAD_MB，无需异步队列）
- 输出纯文本，直接注入对话上下文
- 超长文件截断处理（PARSER_MAX_CHARS 控制）

## 7. 联网搜索

### 方案

- 后端判断用户问题是否需要搜索
- 调用搜索 API 获取结果
- 对结果进行 rerank 筛选
- 将高质量结果注入上下文辅助回答

### 当前实现

- 搜索源：百度搜索 API
- Rerank：阿里云 DashScope（gte-rerank-v2）
- 通过环境变量控制开关和参数

## 8. 会话持久化

- 使用本地 JSON 文件存储会话和消息
- 路径通过 SESSION_STORE_PATH 配置
- 后续可迁移到 SQLite 或 PostgreSQL，但当前阶段文件足够

## 9. 项目结构

```text
apps/
  web/       # Next.js 前端
  api/       # FastAPI 后端
docs/        # 需求与技术文档
scripts/     # 启动与运维脚本
```

## 10. 关键设计决策

### 不用数据库

当前单用户、本地部署，JSON 文件持久化足够。引入数据库增加部署复杂度，收益不大。

### 不用异步队列

文件上传有大小限制（20MB），解析耗时可控，同步处理即可。不需要 Celery/Redis。

### 不做鉴权

单用户本地使用，不暴露公网。无需登录、JWT、权限体系。

### SSE 而非 WebSocket

聊天流式输出是单向的（服务端→客户端），SSE 实现简单，兼容性好，无需 WebSocket。

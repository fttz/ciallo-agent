# 智能聊天助手技术选型

## 1. 选型目标

本选型面向一个“类似豆包 / ChatGPT / 千问 / 元宝”的个人用户向智能聊天助手，要求具备以下特点：

- Web 前端 + 独立后端
- 支持多模型接入
- 支持文本模型和多模态模型
- 支持文件与图片上传
- 支持文件解析与后续问答
- 尽量隐藏复杂配置，优先保证稳定、可扩展、可维护

本次选型优先考虑以下因素：

- 开发效率
- AI 能力生态成熟度
- 文件解析与多模态处理便利性
- 多模型统一接入能力
- 长期可扩展性

## 2. 推荐整体方案

### 2.1 架构结论

推荐采用以下技术组合：

- 前端：Next.js + React + TypeScript
- 后端：FastAPI + Python
- 模型统一接入层：LiteLLM + 自定义 Provider 抽象
- 异步任务：Celery 或 RQ + Redis
- 数据库：PostgreSQL
- 向量检索：pgvector（第二阶段启用）
- 对象存储：S3 兼容存储（开发环境可用 MinIO）
- 实时输出：SSE 优先，必要时补充 WebSocket
- 文件解析：Python 生态解析库 + 统一解析服务
- 部署：Docker Compose 起步，后续可升级 Kubernetes

### 2.2 为什么选这套方案

- 前端使用 Next.js，适合做成熟 Web 应用、首屏优化、路由和服务端渲染能力完整
- 后端使用 Python，原因是模型接入、文件解析、OCR、文档处理、AI 工具链生态更成熟
- 使用 LiteLLM 作为统一模型接入层，可以显著降低对不同模型厂商协议差异的处理成本
- PostgreSQL 同时承担业务数据存储，后续可无缝扩展到 pgvector 做文件检索增强
- Redis 既可做缓存，也可作为异步任务队列基础设施

## 3. 技术栈选型明细

## 3.1 前端

### 推荐

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS 4
- Radix UI 或 shadcn/ui 作为无障碍基础组件来源
- TanStack Query 处理服务端状态
- Zustand 管理轻量客户端状态
- react-markdown + remark-gfm 渲染 AI 输出

### 选择原因

- Next.js 适合做聊天应用、设置页、鉴权页、SEO 页和后续营销页
- TypeScript 有利于保持复杂消息结构、模型配置结构和上传状态的可维护性
- TanStack Query 非常适合处理会话列表、消息记录、上传状态、设置项拉取与刷新
- Zustand 足够轻量，适合管理当前会话、UI 面板状态、上传队列

### 不优先推荐的替代方案

- Vue/Nuxt：可行，但若团队不是 Vue 主栈，AI Web 应用周边生态通常 React 方案更多
- 纯 Vite SPA：开发简单，但后期在鉴权、服务端渲染、SEO、路由和中间层能力上不如 Next.js 完整

## 3.2 后端

### 推荐

- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- Uvicorn / Gunicorn

### 选择原因

- FastAPI 对异步 IO、流式响应、文件上传、OpenAPI 文档、类型约束都很友好
- Python 在 AI 调用、文档解析、多模态处理、OCR、RAG 方面生态最成熟
- Pydantic 对模型配置、消息协议、文件元数据建模效率高

### 不优先推荐的替代方案

- NestJS：工程化体验很好，但文件解析与 AI 生态通常不如 Python 直接
- Go：性能强，但在文档解析、多模型接入和 AI 周边库成熟度上不占优

## 3.3 模型接入层

### 推荐

- LiteLLM 作为统一模型调用适配层
- 在业务后端上再封装一层 Model Gateway

### 推荐能力设计

- Provider 配置抽象：支持 provider、base_url、api_key、models、capabilities
- Model 能力标签：text、vision、reasoning、embedding、audio
- 统一聊天接口：后端只暴露统一的 chat/completions 语义接口
- 统一错误映射：把不同模型厂商错误码归一化
- 能力校验：例如图像输入只能路由到 vision 模型

### 选择原因

- 直接在业务代码里兼容每家协议，维护成本会快速上升
- LiteLLM 能显著缩小 OpenAI 兼容与非兼容模型之间的接入差异
- 业务后端自己保留一层网关封装，可以避免完全受制于第三方库的接口设计

## 3.4 文件上传与存储

### 推荐

- 上传入口通过后端控制权限和校验
- 文件二进制内容存储在 S3 兼容对象存储
- 业务元数据存储在 PostgreSQL

### 推荐存储内容

- 原始文件信息
- 文件类型
- 文件大小
- 上传人
- 上传时间
- 存储地址
- 解析状态
- 解析结果摘要
- 失败原因

### 选择原因

- 对象存储适合承载图片、文档等大文件
- 数据库只保存元数据，避免数据库膨胀
- 后续若迁移到云上 OSS/COS/S3 成本较低

## 3.5 文件解析

### 推荐解析库

- PDF：PyMuPDF 为主，必要时补 pdfplumber
- DOCX：python-docx
- PPTX：python-pptx
- XLSX：openpyxl + pandas
- CSV：pandas
- TXT/MD：原生读取
- JSON：原生 json
- OCR：PaddleOCR 或 Tesseract，首选 PaddleOCR（中文场景更友好）

### 推荐解析架构

- 建立统一 Document Parser 接口
- 每种文件类型一个 Parser 实现
- 输出统一结构：原文、分段、元数据、摘要、表格结构
- 对解析任务走异步队列

### 输出结构建议

- file_id
- mime_type
- extracted_text
- chunks
- metadata
- summary
- parser_name
- parser_status

## 3.6 异步任务与消息流

### 推荐

- Redis
- Celery 或 RQ
- SSE 用于聊天流式输出

### 选择原因

- 文件解析、OCR、大文件摘要不适合全部同步执行
- SSE 对聊天输出足够实用，实现成本低于 WebSocket
- 只有在需要双向长连接能力时，再引入 WebSocket

### 建议分工

- 同步接口：发送消息、拉取会话、拉取设置、上传文件创建记录
- 异步任务：文件解析、OCR、摘要生成、索引构建
- 流式接口：模型输出 token 流

## 3.7 数据存储

### 推荐

- PostgreSQL 16+
- Redis 7+
- pgvector 扩展（第二阶段）

### 核心表建议

- users
- sessions
- messages
- providers
- models
- attachments
- parsed_documents
- model_call_logs
- user_settings

### 为什么不建议首阶段上 Elasticsearch

- 当前核心目标不是复杂全文检索平台
- PostgreSQL + pgvector 足以覆盖第一阶段和第二阶段大多数需求
- 降低系统复杂度，先把聊天、文件解析和模型接入做好更重要

## 3.8 鉴权与安全

### 推荐

- 首阶段采用邮箱验证码或账号密码登录，基于 JWT + Refresh Token
- 若做单用户部署版，可先采用本地管理员账号方案
- API Key 存储必须服务端加密

### 安全措施

- 文件上传白名单校验
- 文件大小限制
- 用户级访问控制，避免跨用户读文件
- 速率限制
- 日志脱敏
- 配置变更审计

## 3.9 可观测性

### 推荐

- 日志：structlog 或标准 logging + JSON 格式
- 指标：Prometheus
- 看板：Grafana
- 错误追踪：Sentry

### 关键指标

- 模型请求次数
- 模型平均耗时
- 模型错误率
- 文件解析成功率
- 平均上传耗时
- 首 token 时间

## 4. 推荐系统架构

## 4.1 逻辑分层

- Web Frontend：聊天 UI、设置页、上传交互、历史会话
- API Backend：鉴权、会话管理、模型路由、上传管理、配置管理
- Model Gateway：统一封装不同模型供应商调用
- Parsing Worker：文件解析、OCR、摘要、索引
- Storage Layer：PostgreSQL、Redis、Object Storage

## 4.2 请求流向

1. 前端发送聊天请求到后端
2. 后端读取会话上下文、附件上下文、模型配置
3. Model Gateway 校验模型能力和输入类型
4. 统一调用 LiteLLM 或特定 Provider 适配器
5. 结果通过 SSE 返回给前端
6. 消息和调用日志入库

## 5. 前后端接口建议

## 5.1 前端调用后端，不直接调用模型供应商

推荐所有模型调用均通过后端完成，不让前端直接使用 API Key。

原因如下：

- 防止 API Key 泄露
- 便于后端统一路由和计费控制
- 便于做模型能力校验与失败重试
- 便于记录日志和做限流

## 5.2 建议核心 API

- POST /api/auth/login
- GET /api/sessions
- POST /api/sessions
- GET /api/sessions/{id}/messages
- POST /api/chat/stream
- POST /api/files/upload
- GET /api/files/{id}
- POST /api/files/{id}/parse
- GET /api/models
- GET /api/settings
- PUT /api/settings
- GET /api/admin/providers
- POST /api/admin/providers

## 6. 关键设计决策

## 6.1 是否采用微服务

不建议首阶段采用微服务。

推荐采用“单体后端 + 异步 Worker”的方式：

- 开发成本更低
- 部署更简单
- 排障更容易
- 对当前业务规模更匹配

后续在模型网关、文件解析、检索服务明显膨胀后，再拆分服务。

## 6.2 是否引入 RAG

建议作为第二阶段增强，而不是第一阶段强依赖。

原因如下：

- 首阶段先满足文件上传、基础解析、摘要问答即可覆盖大部分需求
- 如果过早引入复杂检索链路，会显著增加开发成本和调试成本

## 6.3 是否允许用户自行配置模型 API Key

建议产品设计上预留两种模式：

- 平台托管模式：管理员统一配置模型，普通用户直接使用
- 自带 Key 模式：用户在个人设置中配置自己的供应商 Key

首阶段可以先做平台托管模式，降低复杂度。

## 7. 推荐项目结构

```text
apps/
  web/
  api/
packages/
  shared/
  ui/
infra/
  docker/
docs/
```

### 说明

- apps/web：Next.js 前端
- apps/api：FastAPI 后端
- packages/shared：共享类型、协议定义
- packages/ui：可复用 UI 组件
- infra/docker：本地部署与容器配置
- docs：需求、架构、接口文档

## 8. 开发优先级建议

### 第一优先级

- 用户登录与基础鉴权
- 聊天 UI
- 会话与消息持久化
- 模型配置管理
- 文本模型流式对话

### 第二优先级

- 图片上传与视觉问答
- 文件上传与解析
- 基于解析结果的文件问答
- 设置页

### 第三优先级

- OCR
- RAG
- 多文件聚合问答
- 更细致的模型能力路由
- 监控告警

## 9. 最终推荐结论

如果目标是“尽快做出一个可上线、可扩展、面向普通用户、功能完整但不复杂”的 AI 聊天助手，当前最优解是：

- 前端使用 Next.js + TypeScript
- 后端使用 FastAPI + Python
- 模型统一接入使用 LiteLLM + 自定义网关封装
- PostgreSQL + Redis + S3 兼容对象存储作为基础设施
- 文件解析通过 Python 解析生态和异步任务体系完成
- 第一阶段先做聊天、多模型、图片上传、常见文件解析和设置管理

这套方案在开发效率、功能完整性和长期扩展性之间比较平衡，也最适合你当前描述的产品目标。

## 10. 下一步建议

基于本选型，下一步最值得立刻输出的文档是：

1. 系统架构设计文档
2. 数据库表结构设计
3. API 接口设计草案
4. 第一阶段开发任务拆解
# MarkFold V1 开发文档（Python 版）

## 1. 文档目标

本文档基于 [prd.md](/c:/code/MarkFold/prd.md) 输出，作为当前仓库的实现基线。目标是明确：

- MVP 边界
- Python 技术栈
- 系统架构
- 数据模型
- 核心流程
- 测试与验收方式

## 2. 当前技术方案

### 2.1 技术栈

- 语言：Python 3.12+
- 包管理：`uv`
- API 服务：FastAPI
- Web 管理台：Jinja2 服务端渲染
- CLI：Typer 对话式命令行助手
- ORM：SQLAlchemy 2.0
- 迁移：Alembic
- 数据库：SQLite
- 配置：Pydantic Settings
- 测试：pytest
- 文档存储：本地 Markdown
- 附件存储：本地文件系统
- LLM：仅 OpenAI-compatible provider

### 2.2 项目结构

```text
MarkFold/
  src/markfold/
    api/
    web/
    domain/
    services/
    repositories/
    markdown/
    integrations/llm/
    cli.py
  templates/
  tests/
  alembic/
  vault/
    work-items/
    attachments/
  data/
```

## 3. 架构与核心行为

### 3.1 分层

- 渠道层：Web、CLI、后续飞书
- 核心服务层：命令解析、工作项识别、LLM 结构化、Todo 更新、待确认处理
- 存储层：WorkItem、InputEntry、StructuredEvent、Todo、Attachment、ReviewItem、ChannelContext、InitSession、DocumentSyncJob
- 文档层：Markdown 管理区块渲染与同步

### 3.2 Markdown 策略

- 新建工作项：在 `vault/work-items/` 下创建标准 Markdown 文档
- 导入工作项：保留原文，只在文末追加 `markfold:managed` 管理区块
- 后续同步：只重写管理区块，不覆盖用户原始内容

### 3.3 工作项识别

- 如果用户显式使用 `/use` 设定上下文，则直接使用该工作项
- 否则将候选工作项列表直接交给 LLM 裁决
- 当 LLM 置信度不足时，输入进入 `review_items`

### 3.4 同步可靠性

- 原始输入、结构化事件、Todo、附件先写数据库
- 再生成 `document_sync_jobs`
- 开发期默认同步处理
- 保留 `markfold worker` 用于补偿与重试

### 3.5 初始化工作项

- `/init` 不再直接创建空工作项，而是开启一个 `init_sessions`
- LLM 逐轮补全标题、目标、背景、待办、风险、备注等草稿字段
- 当草稿信息足够时，自动创建工作项并把初始化内容写入首版 Markdown
- 用户也可以显式使用 `/finish-init` 或 `/cancel-init`

## 4. 已实现范围

### 4.1 API

- `POST /api/inputs`
- `POST /api/work-items/import`
- `POST /api/commands/init`
- `POST /api/commands/use`
- `POST /api/commands/todo`
- `POST /api/commands/done`
- `GET /api/work-items`
- `GET /api/work-items/{id}`
- `GET /api/todos`
- `GET /api/queries/daily-summary`
- `GET /api/queries/work-item-status`
- `GET /api/reviews`
- `POST /api/reviews/{id}/resolve`

### 4.2 CLI

- `markfold`
  - 默认直接进入对话模式
- `markfold chat`
  - 显式进入对话模式
- `markfold init`
- `markfold import`
- `markfold send`
- `markfold status`
- `markfold yesterday`
- `markfold worker`
- `markfold todo list`
- `markfold-feishu`

### 4.3 Web 管理台

- 工作项列表
- 工作项详情
- 导入页面
- 待确认页面
- 查询页面

### 4.4 MVP 约束

- 单用户
- 单 Vault
- 本地文件存储
- 不做 OCR
- 不做向量检索

### 4.5 已实现的飞书入口

- 使用飞书企业自建应用的 WebSocket 长连接模式接入
- 独立进程命令为 `markfold-feishu`
- 支持 `im.message.receive_v1`
- 支持 `text`、`image`、`file` 三类消息
- 按 `chat_id` 维护上下文，和 CLI/Web 的核心归档链路共用同一套服务
- 群聊默认仅在 `@机器人` 时处理

## 5. 测试与验收

### 5.1 已覆盖测试

- 命令解析
- Markdown 管理区块更新
- 文本输入归档与文档同步
- 低置信度输入进入待确认
- 导入 Markdown 并补充管理区块
- 图片附件输入写入文档
- 渐进式初始化会话自动生成首版工作项文档
- 飞书长连接 ACK、私聊文本、群聊提及过滤

### 5.2 验收标准

- 能通过 LLM 引导式对话创建新工作项并生成 Markdown
- 能导入已有 Markdown
- 能归档自然语言文本并维护 Todo
- 能处理图片附件
- 能查询昨日回顾和未完成 Todo
- 能把低置信度输入送入人工确认队列

## 6. 下一阶段

- 飞书加密事件与更多消息类型
- 更强的纠错指令
- 更细的工作项状态页
- PostgreSQL 迁移支持
- 更稳定的 OpenAI JSON 输出契约

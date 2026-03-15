# MarkFold

MarkFold 是一个基于 Python 的个人工作记录助手。它的目标不是替代你的 Markdown 知识库，而是在你日常用自然语言记录碎片信息时，自动帮你完成以下事情：

- 识别这条输入属于哪个工作项
- 从输入中提炼结构化事件
- 自动维护 Todo 状态
- 把结果同步写入对应的 Markdown 文档
- 保留原始输入、附件、结构化结果，方便追溯和纠错

当前版本是一个面向单用户、单 Vault 的 MVP，重点验证“想到就发，自动沉淀到 Markdown”这条主链路。

## 1. 项目定位

这个项目适合下面几类使用方式：

- 你同时跟进多个项目，希望用一句自然语言快速记录进展
- 你已经有自己的 Markdown 文档，希望导入后继续维护
- 你不想每次手动整理 Todo、进展、决策、阻塞
- 你希望后续把同一套能力接到 Web、CLI、飞书等入口

MarkFold 当前不会尝试做复杂协作、权限系统、OCR、富文本回写，而是先把个人版 MVP 做稳定。

## 2. 当前能力

当前实现已经包含这些核心能力：

- 新建工作项
  - 通过 CLI 或 API 启动一个由 LLM 引导的初始化会话
  - 渐进式补充标题、目标、背景、待办、风险、备注
  - 信息足够时自动生成首版 Markdown 文档
- 导入已有 Markdown
  - 保留原文
  - 在文末追加 MarkFold 管理区块
  - 后续系统写入只更新管理区块
- 文本归档
  - 接收自然语言输入
  - 提炼为 `progress`、`todo_created`、`todo_completed`、`risk`、`decision`、`note`
- 图片附件归档
  - 图片保存到本地附件目录
  - 在对应 Markdown 中写入附件记录
- Todo 管理
  - 自动新增 Todo
  - 自动尝试完成已有 Todo
  - 支持查询未完成 Todo
- 待确认机制
  - 当工作项识别置信度过低时，进入待确认队列
  - 支持在 Web 管理台中人工修正
- 多入口
  - HTTP API
  - Web 管理台
  - 对话式 CLI
  - 飞书机器人 WebSocket 长连接

## 3. 技术栈

项目当前采用全 Python 技术栈，尽量降低学习成本和维护复杂度。

- Python 3.12+
- `uv` 作为包管理与运行工具
- FastAPI 作为 API 与 Web 容器
- Jinja2 作为服务端渲染模板引擎
- Typer 作为 CLI 框架
- SQLAlchemy 2.0 作为 ORM
- Alembic 作为迁移工具
- SQLite 作为默认数据库
- Pydantic Settings 作为配置管理
- pytest 作为测试框架

LLM 部分现在只保留一条路径：

- `openai`
  - 使用 OpenAI Python SDK
  - 支持 OpenAI-compatible 网关
  - 普通输入的事件提取与工作项选择都只依赖 LLM

## 4. 项目结构

```text
MarkFold/
  alembic/                  # 数据库迁移
  docs/                     # 开发文档
  src/markfold/
    api/                    # FastAPI API 路由与应用入口
    web/                    # Web 页面路由
    domain/                 # 枚举、Pydantic 模型
    services/               # 核心业务逻辑
    repositories/           # 数据库模型与仓储
    markdown/               # Markdown 管理区块渲染与同步
    integrations/llm/       # LLM 抽象与实现
    cli.py                  # CLI 入口
  templates/                # Jinja2 页面模板
  tests/                    # 测试
  vault/
    work-items/             # 新建工作项 Markdown 文档
    attachments/            # 附件
  data/                     # SQLite 数据库文件
  prd.md                    # 原始需求文档
```

## 5. 数据流概览

MarkFold 的主流程大致如下：

1. 用户从 CLI、Web 或后续飞书入口发送一条输入
2. 系统先保存原始输入 `InputEntry`
3. 如果有附件，先保存附件并建立关联
4. 识别这是普通输入还是显式命令
5. 如果是普通输入：
   - 使用 LLM 识别工作项
   - 使用 LLM 提取结构化事件
   - 更新 Todo
   - 生成文档同步任务
6. 如果是 `/init` 初始化输入：
   - 进入 `init_sessions`
   - 使用 LLM 按轮次补全工作项草稿
   - 信息足够后创建工作项并写入首版结构化内容
7. 如果识别置信度过低：
   - 进入待确认队列
   - 等待人工修正
8. 文档同步模块将结构化结果写入 Markdown 管理区块

这样做的目的是保证：

- 原始输入可追溯
- 结构化结果不依赖 Markdown 是否写入成功
- 文档同步失败时可以重试

## 6. 安装与启动

### 6.1 环境要求

- Python 3.12 或更高版本
- 已安装 `uv`

如果你还没有安装 `uv`，可以参考它的官方安装方式；当前项目默认使用 `uv` 来创建虚拟环境、安装依赖和运行命令。

### 6.2 安装依赖

在项目根目录执行：

```bash
uv sync
```

这会自动：

- 创建虚拟环境
- 安装运行依赖
- 安装开发依赖
- 生成或更新 `uv.lock`

### 6.3 配置环境变量

把 `.env.example` 复制为 `.env`，然后按需要修改：

```env
MARKFOLD_DEBUG=false
MARKFOLD_DATABASE_URL=sqlite:///data/markfold.db
MARKFOLD_VAULT_ROOT=vault
MARKFOLD_API_HOST=127.0.0.1
MARKFOLD_API_PORT=8000
MARKFOLD_OPENAI_API_KEY=
MARKFOLD_OPENAI_BASE_URL=
MARKFOLD_OPENAI_MODEL=
MARKFOLD_FEISHU_APP_ID=
MARKFOLD_FEISHU_APP_SECRET=
MARKFOLD_FEISHU_BASE_URL=https://open.feishu.cn
```

关键字段说明：

- `MARKFOLD_DATABASE_URL`
  - 默认使用本地 SQLite
- `MARKFOLD_VAULT_ROOT`
  - Markdown 和附件的根目录
- `MARKFOLD_API_HOST`
  - Web/API 服务监听地址
- `MARKFOLD_API_PORT`
  - Web/API 服务监听端口
- `MARKFOLD_OPENAI_API_KEY`
  - 必填
- `MARKFOLD_OPENAI_BASE_URL`
  - 可选，用于兼容第三方网关
- `MARKFOLD_OPENAI_MODEL`
  - 可选，指定模型名
- `MARKFOLD_FEISHU_APP_ID`
  - 飞书企业自建应用的 App ID
- `MARKFOLD_FEISHU_APP_SECRET`
  - 飞书企业自建应用的 App Secret
- `MARKFOLD_FEISHU_BASE_URL`
  - 飞书开放平台 API 地址，默认 `https://open.feishu.cn`

注意：

- 当前版本已经删除本地 heuristic 规则分支
- 普通输入必须依赖 LLM
- 如果没有配置 `MARKFOLD_OPENAI_API_KEY`，普通归档输入会直接报错

### 6.4 启动对话式 CLI

```bash
uv run markfold
```

执行后会直接进入一个终端里的助手对话界面，你可以持续输入自然语言或命令，例如：

```text
助手 > 已进入 MarkFold 对话模式。直接输入你的记录即可。输入 /help 查看帮助，输入 /exit 退出。
你 > /init 项目A
你 > 目标是先把 MVP 跑起来
你 > 背景是这是一个用于归档 IDE 对话和任务进展的工具
你 > 待办是补日志、补监控
你 > /finish-init
你 > 今天把接口联调跑通了，还要补错误处理
你 > /attach "C:\tmp\screenshot.png"
```

这是 CLI 的主要使用方式，也是当前最接近“和助手聊天”的入口。

### 6.5 启动 Web/API 服务

如果你需要 Web 管理台，再单独启动：

```bash
uv run markfold-api
```

启动后默认访问地址为：

```text
http://127.0.0.1:8000/
```

Web 管理台和 API 都挂在这一个服务里。注意，单独使用 CLI 对话模式时，不需要先启动这个服务。

### 6.6 接入飞书

这一版已经改成“飞书企业自建应用 + WebSocket 长连接”接入。完成后，你可以直接在飞书里给机器人发消息，本地调试不需要再做内网穿透。

你需要先准备：

- 一个飞书企业自建应用
- 已启用机器人能力
- 已在 `.env` 中配置好以下字段

```env
MARKFOLD_FEISHU_APP_ID=cli_aabbccddeeff
MARKFOLD_FEISHU_APP_SECRET=你的飞书应用密钥
MARKFOLD_FEISHU_BASE_URL=https://open.feishu.cn
```

然后在飞书开放平台里完成这些设置：

1. 把飞书应用的事件接收方式切到“使用长连接接收事件”
2. 启动 MarkFold 的飞书 worker：

```bash
uv run markfold-feishu
```

3. 同时如果你要用 Web 管理台，再额外启动：

```bash
uv run markfold-api
```

4. 订阅事件 `im.message.receive_v1`
5. 给应用开通“发送消息”和“获取消息资源”相关权限
6. 把机器人加入你要使用的私聊或群聊

当前实现支持这些飞书消息类型：

- `text`
  - 直接作为普通对话输入处理
- `image`
  - 会先从飞书下载图片，再作为附件归档
- `file`
  - 会先从飞书下载文件，再作为附件归档

飞书上下文会按 `chat_id` 隔离，也就是说：

- 同一个飞书会话里的 `/use`、`/init`、`/finish-init` 会持续生效
- 不同群聊或不同私聊之间不会串上下文
- 群聊里默认只有 `@机器人` 时才会处理消息

一个典型使用流程如下：

```text
/init IDE 助手接入
目标是先把飞书入口打通
背景是希望以后直接在飞书里给机器人发记录
待办是接消息、回消息、下载图片
今天先把长连接模式跑通了
```

## 7. CLI 使用说明

### 7.1 推荐方式：直接进入对话模式

```bash
uv run markfold
```

或者显式执行：

```bash
uv run markfold chat
```

进入对话模式后，你可以像和助手聊天一样连续输入内容。当前支持两类输入：

- 自然语言
  - 例如：`今天把项目A接口联调跑通了，还要补错误处理`
- 斜杠命令
  - 例如：`/init 项目A`
  - 例如：`/finish-init`
  - 例如：`/cancel-init`
  - 例如：`/use 项目A`
  - 例如：`/todo 补日志`
  - 例如：`/done 补日志`

对话模式下还额外支持几条会话命令：

- `/help`
  - 查看帮助
- `/workitems`
  - 查看当前所有工作项
- `/todos`
  - 查看当前上下文或全局未完成 Todo
- `/yesterday`
  - 查看昨天的结构化回顾
- `/attach <文件路径>`
  - 发送一个附件到当前上下文
- `/exit`
  - 退出对话

### 7.2 渐进式初始化工作项

```bash
uv run markfold init "项目A"
```

也可以附带目标和状态：

```bash
uv run markfold init "项目A" --goal "完成 MVP" --status active
```

这个命令现在会直接进入一个对话式初始化流程，而不是立刻创建一个空工作项。系统会把你提供的种子信息先交给 LLM，然后继续追问缺失字段。

典型流程如下：

```text
你 > /init 项目A
助手 > 这个工作项当前最重要的目标是什么？
你 > 目标是先把 MVP 跑起来
助手 > 补一句背景信息吧，我会把它写进首版文档。
你 > 背景是这是一个用于归档 IDE 对话和任务进展的工具
你 > 待办是补日志、补监控
助手 > 已根据对话创建工作项：项目A
```

在初始化会话中，你可以：

- 继续自然语言补充信息，LLM 会持续更新草稿
- 使用 `/finish-init` 立即按当前草稿创建文档
- 使用 `/cancel-init` 放弃这次初始化

当信息足够时，系统会：

- 创建数据库中的工作项记录
- 在 `vault/work-items/` 下生成 Markdown 文档
- 把背景、目标、待办、风险、备注写入结构化内容
- 把当前上下文切到这个新工作项

如果你已经在对话模式里，更推荐直接输入：

```text
/init 项目A
```

### 7.3 导入已有 Markdown

```bash
uv run markfold import ./notes/project-a.md
```

导入后系统会：

- 从 Markdown 中尝试提取标题
- 提取 checklist 形式的 Todo
- 保留原始内容
- 在文末追加 MarkFold 管理区块

### 7.4 发送普通记录

```bash
uv run markfold send "今天把项目A接口联调跑通了，还要补错误处理"
```

这个命令主要用于脚本化调用、自动化测试或一次性输入。日常使用时，更推荐直接进入 `uv run markfold` 对话模式。

系统会尝试把这句话拆成多个事件，例如：

- 一个进展事件
- 一个新 Todo 事件

如果当前上下文明确，系统会直接归档；如果不明确，可能进入待确认队列。

### 7.5 显式命令

以下命令也可以直接通过 `send` 发送：

```bash
uv run markfold send "/use 项目A"
uv run markfold send "/todo 补充异常处理"
uv run markfold send "/done 补充异常处理"
uv run markfold send "/status 项目A"
uv run markfold send "/init 项目B"
```

其中：

- `/use`：切换当前上下文工作项
- `/todo`：显式新增 Todo
- `/done`：显式完成 Todo
- `/status`：查询工作项状态
- `/init`：创建新工作项

### 7.6 查询 Todo

```bash
uv run markfold todo list
```

如果只看某个工作项，也可以传 `work_item_id`。

### 7.7 查看工作项状态

```bash
uv run markfold status "项目A"
```

输出包括：

- 工作项基本信息
- 当前未完成 Todo
- 最近事件

### 7.8 昨日回顾

```bash
uv run markfold yesterday
```

也支持指定日期：

```bash
uv run markfold yesterday --target-date 2026-03-15
```

### 7.9 手动执行文档同步任务

```bash
uv run markfold worker
```

这个命令主要用于：

- 文档同步失败后的补偿
- 批量处理待同步任务
- 调试 Markdown 写入逻辑

## 8. Web 管理台

启动服务后，打开：

```text
http://127.0.0.1:8000/
```

当前页面包括：

- 工作项首页
  - 查看所有工作项
  - 查看未完成 Todo
  - 查看待确认队列
- 工作项详情页
  - 查看当前工作项状态
  - 发送新记录到该工作项
  - 直接预览 Markdown 内容
- 导入页
  - 输入一个本地 Markdown 路径进行导入
- 待确认页
  - 对低置信度输入进行人工绑定
- 查询页
  - 查看某天的回顾
  - 查看当前未完成 Todo

当前 Web 管理台是轻量管理界面，不是聊天式复杂工作台，目的是先把管理、纠错和查询路径跑通。

## 9. Markdown 同步规则

### 9.1 新建工作项

新建工作项会直接生成标准 Markdown 文档，内容包括：

- 基本信息
- 当前目标
- 最新进展
- 当前 Todo
- 已完成事项
- 风险 / 阻塞
- 决策 / 备注
- 附件记录

### 9.2 导入工作项

导入已有 Markdown 时，不会重写原文，而是在文末追加：

```md
<!-- markfold:managed:start -->
...
<!-- markfold:managed:end -->
```

后续系统只维护这一段内容。

### 9.3 事件映射

不同结构化事件会写入不同区块：

- `progress` -> 最新进展
- `todo_created` -> 当前 Todo
- `todo_completed` -> 已完成事项，并尝试从当前 Todo 中移除
- `risk` -> 风险 / 阻塞
- `decision` -> 决策 / 备注
- `note` -> 决策 / 备注
- 附件 -> 附件记录

## 10. LLM 与工作项识别

### 10.1 当前识别逻辑

工作项识别现在只有两条路径：

1. 如果你显式通过 `/use` 设定了当前上下文，直接使用该工作项
2. 如果没有显式上下文，则把候选工作项列表交给 LLM 选择

### 10.2 低置信度处理

如果识别结果不可靠：

- 输入会先被保存
- 结构化结果也会暂存
- 但不会立即绑定到某个工作项
- 系统会创建一条待确认记录
- 需要在 Web 管理台里手工确认

### 10.3 当前 LLM 模式

当前只支持 OpenAI-compatible LLM。

- 不再提供 heuristic fallback
- 不再使用本地规则来提取普通输入事件
- 不再使用本地规则来猜测工作项归属

## 11. 测试

运行测试：

```bash
uv run pytest
```

当前测试已经覆盖：

- 命令解析
- Markdown 管理区块替换
- 文本输入归档
- Todo 自动维护
- 低置信度进入待确认
- 导入 Markdown
- 图片附件写入文档
- 飞书长连接 ACK、文字消息、群聊提及过滤

## 12. 当前限制

当前版本有一些明确的边界：

- 仅支持单用户
- 仅支持单 Vault
- 默认数据库是 SQLite
- 不支持多人协作
- 不支持 OCR
- 不支持图片内容理解
- 不支持向量检索
- 飞书长连接暂不支持卡片 callback 扩展

这些限制是刻意保留的，目的是先让核心归档链路稳定。

## 13. 后续计划

下一阶段可以继续补这些能力：

- 飞书加密事件与更多消息类型
- 更细的纠错命令
- 更强的工作项识别策略
- PostgreSQL 支持
- 更稳定的 OpenAI JSON 输出校验
- 更完整的 Web 工作台

## 14. 常用命令速查

```bash
uv sync
uv run markfold-api
uv run markfold-feishu
uv run markfold init "项目A"
uv run markfold import ./notes/project-a.md
uv run markfold send "今天把接口联调跑通了，还要补错误处理"
uv run markfold send "/init 项目A"
uv run markfold send "目标是先把 MVP 跑起来" --context-key cli:init
uv run markfold send "/finish-init" --context-key cli:init
uv run markfold send "/use 项目A"
uv run markfold send "/todo 补日志与监控"
uv run markfold send "/done 补日志与监控"
uv run markfold status "项目A"
uv run markfold todo list
uv run markfold yesterday
uv run markfold worker
uv run pytest
```

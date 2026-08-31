# Coding Agent WebUI 设计文档

## 概述

为 `nju-coding-agent-harness` 增加 Web 界面，用户可以在浏览器中与 LLM 对话，LLM 在用户本机执行代码/工具操作。界面类似 opencode 的左右分栏布局，支持流式输出、工具调用可视化和多轮对话上下文保持。

## 架构

```
┌─────────────────────┐     WebSocket (ws://localhost:8756/ws)     ┌──────────────────────┐
│   浏览器 (index.html) │ ◄──────────────────────────────────────► │  FastAPI Server       │
│   Vanilla JS SPA     │     REST (http://localhost:8756/api/*)   │  harness/webui/       │
└─────────────────────┘                                           └──────────────────────┘
```

- **后端**: FastAPI + WebSocket，运行在 `localhost:8756`
- **前端**: 单文件 HTML (Vanilla JS)，无构建步骤
- **通信**: WebSocket 承载流式聊天，REST 承载文件浏览/配置

## 后端设计

### 新增文件

| 文件 | 说明 |
|------|------|
| `harness/webui/__init__.py` | 空 |
| `harness/webui/server.py` | FastAPI 应用，WebSocket + REST 端点 |
| `harness/webui/static/index.html` | 前端 SPA（单文件） |
| `harness/webui/stream_agent.py` | 流式 Agent 包装器 |

### 流式 Agent 包装器 (`stream_agent.py`)

复用现有 `Agent` 类，新增 `chat()` 方法支持多轮对话：

```python
class StreamAgent:
    """WebSocket 会话的 Agent 包装器，支持多轮对话和流式推送。"""

    def __init__(self, config: Config):
        # 复用 main.py 的 make_agent 逻辑组装 Agent
        ...

    async def chat(self, message: str, push: Callable[[dict], Awaitable[None]]):
        """处理用户消息，通过 push 回调逐条推送事件到 WebSocket。"""
        # 1. 构建 messages: 已有历史 + 新用户消息
        # 2. 调用 llm.complete_stream() 获取流式响应
        # 3. 逐 token 推送 { type: "token", content: "..." }
        # 4. 处理 tool_calls，推送 { type: "tool_call", ... }
        # 5. 推送 { type: "tool_output", ... }
        # 6. 推送 { type: "done" }
```

### Agent 改造点

现有 `Agent.run()` 每次构建新 messages 列表。WebUI 需要保持上下文：

1. `Agent.messages` 属性已在 `__init__` 中定义为 `list[dict]`，`_finish()` 中已赋值 `self.messages = messages`
2. 新增 `Agent.chat(message)` 方法，在 `self.messages` 基础上追加用户消息并继续 LLM 循环
3. `LLM.complete()` 需改为 `complete_stream()` 以支持逐 token 回调（或新增流式版本）

### LLM 流式改造

当前 `OpenAILLM.complete()` 内部已使用流式 API，但聚合后返回完整结果。改造为流式版本：

```python
class OpenAILLM:
    def complete_stream(self, messages, tools):
        """生成器，逐个产出 (type, data) 元组。"""
        stream = self._create_stream(messages, tools)
        text_parts = []
        tool_acc = {}
        for chunk in stream:
            # 解析 delta，产出 token 或 tool_call delta
            ...
        # 最终产出完整结果
```

### WebSocket 消息协议

```
客户端 → 服务端:
{ type: "chat",    content: "写一个排序算法" }
{ type: "stop" }

服务端 → 客户端:
{ type: "token",       content: "我" }           # LLM 逐 token
{ type: "tool_call",   name: "bash", input: "..." }  # 工具调用开始
{ type: "tool_output", name: "bash", content: "..." } # 工具执行结果
{ type: "done" }                                   # 本轮结束
{ type: "error",       content: "..." }             # 错误
```

### REST 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/files` | 列出目录内容（`?path=...`） |
| GET | `/api/files/read` | 读取文件内容（`?path=...`） |
| GET | `/api/config` | 获取当前配置 |
| POST | `/api/config` | 更新配置 |
| POST | `/api/stop` | 停止当前生成 |

### 启动方式

新增 CLI 参数 `--web`：

```bash
cah --web                    # 默认端口 8756
cah --web --port 8080        # 指定端口
```

`main.py` 新增 `--web` 参数，启动 FastAPI 服务器。

## 前端设计

### 布局

```
┌──────────────────────────────────────────────────┐
│  ┌── 侧边栏 (256px, 可折叠) ──┬── 主区域 ──────── │
│  │                            │                  │
│  │  ● 新建对话                │  消息流           │
│  │  ● 对话历史列表            │  ┌──────────────┐ │
│  │  ● 文件浏览器              │  │ 用户消息 (右) │ │
│  │  ● 设置                    │  └──────────────┘ │
│  │                            │  ┌──────────────┐ │
│  │  ─── 工作区 ───            │  │ LLM 回复      │ │
│  │  Coding-Agent              │  │ - markdown    │ │
│  │                            │  │ - 代码高亮    │ │
│  │                            │  └──────────────┘ │
│  │                            │  ┌ bash ────────┐ │ │
│  │                            │  │ 工具调用卡片   │ │ │
│  │                            │  └──────────────┘ │ │
│  │                            │                  │ │
│  │                            ├── 输入区 ──────── │ │
│  │                            │ [输入框...] [发送] │ │
│  └────────────────────────────┴──────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 核心组件

1. **侧边栏**: 对话列表（新建/切换）、文件浏览器树、设置入口。可折叠（按钮在左上角）。
2. **消息流**: 用户消息右对齐（浅色背景），LLM 回复左对齐（无背景），markdown 渲染 + 代码语法高亮。
3. **工具卡片**: 每个工具调用显示为折叠卡片，左边框颜色区分类型（bash=绿色, 文件=蓝色, web=紫色, 其他=灰色）。标题行显示工具名和输入预览，点击展开/折叠。执行中显示旋转加载图标。
4. **输入区**: 底部固定，多行文本框，Enter 发送，Shift+Enter 换行。发送中显示停止按钮替代发送按钮。
5. **文件浏览器**: 侧边栏切换模式，树形目录结构，点击文件名在右侧预览面板中显示内容（语法高亮）。
6. **设置面板**: 模态框，包含模型选择、API Key、sandbox 模式、主题切换。

### 视觉风格

- 主色调：暗色主题（类似 VS Code 暗色），配浅色主题切换
- 字体：系统无衬线字体（-apple-system, Segoe UI, sans-serif），代码块用等宽字体
- 背景：`#1a1a2e`（暗色主背景），`#16213e`（侧边栏），`#0f3460`（强调色）
- 消息：用户消息 `#2a2a4a` 背景，LLM 回复无背景
- 工具卡片：折叠态显示工具名 + 输入预览，展开态显示完整输入/输出
- 代码高亮：使用 highlight.js 或手写简单高亮

### 数据流

1. 用户输入消息 → WebSocket 发送 `{ type: "chat", content: "..." }`
2. 服务端 StreamAgent 处理 → 逐 event 推送
3. 前端收到 `token` → 追加到当前消息气泡，实时渲染 markdown
4. 前端收到 `tool_call` → 创建工具卡片（折叠态，加载中）
5. 前端收到 `tool_output` → 展开工具卡片，显示输出
6. 前端收到 `done` → 结束本轮，输入框可用
7. 前端收到 `error` → 显示错误提示

### 停止生成

- 用户点击停止按钮 → WebSocket 发送 `{ type: "stop" }`
- 服务端中断当前 agent 处理
- 前端保留已收到的所有内容

## 依赖变更

`pyproject.toml` 新增依赖：

```toml
dependencies = [
    ...,
    "fastapi",
    "uvicorn",
    "websockets",
    "python-multipart",
]
```

## 文件结构

```
harness/
├── webui/
│   ├── __init__.py
│   ├── server.py          # FastAPI 应用
│   ├── stream_agent.py    # 流式 Agent 包装器
│   └── static/
│       └── index.html     # 前端 SPA
├── agent.py               # 修改：新增 chat() 方法
├── llm.py                 # 修改：新增 complete_stream() 方法
├── main.py                # 修改：新增 --web 参数
...
```

## 实施顺序

1. `llm.py`: 新增 `complete_stream()` 流式方法
2. `agent.py`: 新增 `chat()` 多轮对话方法
3. `webui/stream_agent.py`: 流式 Agent 包装器
4. `webui/server.py`: FastAPI 服务器
5. `webui/static/index.html`: 前端 SPA
6. `main.py`: 新增 `--web` 启动参数
7. `pyproject.toml`: 新增依赖
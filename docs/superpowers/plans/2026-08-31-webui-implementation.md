# WebUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web-based UI (`cah --web`) to the coding agent harness, enabling browser-based chat with LLM, tool call visualization, file browsing, and settings.

**Architecture:** FastAPI server with WebSocket for streaming chat, REST for file/config operations. Single-file Vanilla JS frontend (no build step). Agent instance persists per WebSocket connection for multi-turn context.

**Tech Stack:** FastAPI, Uvicorn, WebSocket, Vanilla JS, highlight.js (code highlighting)

**Spec:** `docs/superpowers/specs/2026-08-31-webui-design.md`

## Global Constraints

- All new dependencies: `fastapi`, `uvicorn`, `websockets`, `python-multipart`
- Agent must maintain conversation context across multiple `chat()` calls
- Frontend must be a single self-contained HTML file (no build step)
- WebSocket port default: 8756
- All user-visible copy in Simplified Chinese
- Must preserve all existing CLI functionality (`cah` without `--web`)
- All existing tests must continue to pass

---

### Task 1: Add `complete_stream()` to `OpenAILLM`

**Files:**
- Modify: `harness/llm.py`
- Test: `harness/tests/test_llm.py`

**Interfaces:**
- Consumes: `OpenAILLM(messages, tools)` — same args as `complete()`
- Produces: `complete_stream(messages, tools) -> Generator[tuple[str, dict], None, None]` — yields `(event_type, data)` tuples

Event types:
- `("token", {"content": "..."})` — a text token
- `("tool_call_delta", {"index": 0, "name": "...", "arguments": "..."})` — partial tool call chunk
- `("tool_calls", {"tool_calls": [...]})` — complete tool calls (after stream ends)
- `("done", {"text": "...", "tool_calls": [...]})` — stream complete

- [ ] **Step 1: Write the failing test for `complete_stream`**

```python
def test_complete_stream_tokens():
    import httpx
    payload = [
        {"choices": [{"delta": {"content": "你好"}}]},
        {"choices": [{"delta": {"content": "世界"}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    lines = "\n\n".join(f"data: {json.dumps(c)}" for c in payload) + "\n\ndata: [DONE]\n\n"
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=lines, headers={"Content-Type": "text/event-stream"})))
    llm = OpenAILLM("test-key", http_client=client)
    events = list(llm.complete_stream([{"role": "user", "content": "x"}], []))
    tokens = [e[1]["content"] for e in events if e[0] == "token"]
    assert "".join(tokens) == "你好世界"


def test_complete_stream_tool_calls():
    import httpx
    payload = [
        {"choices": [{"delta": {"content": "让我查一下"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "bash", "arguments": ""}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"comm'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'and": "ls"}'}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    lines = "\n\n".join(f"data: {json.dumps(c)}" for c in payload) + "\n\ndata: [DONE]\n\n"
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=lines, headers={"Content-Type": "text/event-stream"})))
    llm = OpenAILLM("test-key", http_client=client)
    events = list(llm.complete_stream([{"role": "user", "content": "x"}], []))
    tokens = [e[1]["content"] for e in events if e[0] == "token"]
    done_events = [e for e in events if e[0] == "done"]
    assert "".join(tokens) == "让我查一下"
    assert len(done_events) == 1
    assert done_events[0][1]["tool_calls"] == [{"name": "bash", "arguments": {"command": "ls"}}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest harness/tests/test_llm.py::test_complete_stream_tokens harness/tests/test_llm.py::test_complete_stream_tool_calls -v`
Expected: FAIL with "OpenAILLM object has no attribute 'complete_stream'"

- [ ] **Step 3: Implement `complete_stream` in `OpenAILLM`**

Add after the existing `complete()` method:

```python
def complete_stream(self, messages: list[dict], tools: list[dict]):
    stream = self._create_stream(messages, tools)
    text_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta and delta.content:
            text_parts.append(delta.content)
            yield ("token", {"content": delta.content})
        if delta and delta.tool_calls:
            for call in delta.tool_calls:
                slot = tool_acc.setdefault(call.index, {"name": "", "arguments": ""})
                if call.function and call.function.name:
                    slot["name"] += call.function.name
                if call.function and call.function.arguments:
                    slot["arguments"] += call.function.arguments
                yield ("tool_call_delta", {"index": call.index, "name": slot["name"], "arguments": slot["arguments"]})
    text = "".join(text_parts)
    tool_calls: list[dict] = []
    for index in sorted(tool_acc):
        slot = tool_acc[index]
        try:
            arguments = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            arguments = {}
        tool_calls.append({"name": slot["name"], "arguments": arguments})
    usage = {"approx_tokens": self._approx_tokens(text, tool_calls)}
    yield ("done", {"text": text, "tool_calls": tool_calls, "usage": usage})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest harness/tests/test_llm.py::test_complete_stream_tokens harness/tests/test_llm.py::test_complete_stream_tool_calls -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests**

Run: `pytest harness/tests/ -q`
Expected: All tests pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add harness/llm.py harness/tests/test_llm.py
git commit -m "feat: add complete_stream() to OpenAILLM"
```

---

### Task 2: Add `chat()` to `Agent`

**Files:**
- Modify: `harness/agent.py`
- Test: `harness/tests/test_agent_core.py`

**Interfaces:**
- Consumes: `Agent.chat(message: str, on_event: Callable[[str, dict], None] | None = None) -> AgentResult`
- Produces: `AgentResult` with accumulated messages in `self.messages`

`chat()` differs from `run()`:
- Does NOT rebuild system prompt or memory — continues from `self.messages`
- Uses `complete_stream` internally, calling `on_event(event_type, data)` for each event
- After completion, `self.messages` contains the full conversation history
- Memory consolidation happens only after `run()` (not `chat()`) to avoid repeated consolidation

- [ ] **Step 1: Write the failing test**

```python
def test_chat_preserves_context(tmp_path):
    from harness.fake_llm import FakeLLM, FakeTurn
    from harness.agent import Agent
    from harness.config import Config
    from harness.hooks import HookBus
    from harness.policy import Policy
    from harness.registry import make_registry
    from harness.sandbox import LocalSandbox
    from harness.state import StateMachine
    from harness.tools.bash import spec as bash_spec

    sb = LocalSandbox()
    cfg = Config(workspace=tmp_path, tool_timeout=5)
    reg = make_registry([bash_spec()])
    llm = FakeLLM([
        FakeTurn(text="第一次回复"),
        FakeTurn(text="第二次回复"),
    ])
    a = Agent(llm, reg, sb, HookBus(), Policy(), StateMachine(), None, cfg)
    # Use chat() twice
    r1 = a.chat("第一条消息")
    assert "第一次回复" in r1.text
    assert len(a.messages) >= 4  # system + user1 + asst1 (+ maybe extra)
    r2 = a.chat("第二条消息")
    assert "第二次回复" in r2.text
    # Verify context was preserved: messages should include both rounds
    user_msgs = [m for m in a.messages if m.get("role") == "user"]
    assert len(user_msgs) == 2
    assert user_msgs[0]["content"] == "第一条消息"
    assert user_msgs[1]["content"] == "第二条消息"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest harness/tests/test_agent_core.py::test_chat_preserves_context -v`
Expected: FAIL with "Agent object has no attribute 'chat'"

- [ ] **Step 3: Implement `chat()` in `Agent`**

Add after the existing `run()` method:

```python
def chat(self, message: str, on_event: Callable[[str, dict], None] | None = None) -> AgentResult:
    """多轮对话：在 self.messages 基础上追加用户消息并继续 LLM 循环。"""
    result = AgentResult()
    self.state.fire("task_submitted", "loop")
    if not self.messages:
        self.messages = [
            {"role": "system", "content": build_system_prompt(self.config)},
        ]
        if self.memory is not None:
            for chunk in self.memory.top_k_chunks(message):
                self.messages.append(
                    {"role": "system", "content": f"[memory] {chunk['chunk']}"}
                )
    self.messages.append({"role": "user", "content": message})
    call_uid = len(self._tool_calls)
    fail_seq = 0
    fail_tool: str | None = None
    max_fail_seq = 0
    self._compress_calls = 0
    while result.steps_used < self.config.max_steps:
        if self._check_budget(self.messages):
            self.messages = self._compress(self.messages)
        response = self.llm.complete(self.messages, build_request_tools(self.registry))
        result.steps_used += 1
        if not response.tool_calls:
            final = response.text or "任务完成"
            self.messages.append({"role": "assistant", "content": final})
            result.text = final
            if on_event:
                on_event("token", {"content": final})
            return self._finish(result, self.messages, max_fail_seq)
        if on_event and response.text:
            on_event("token", {"content": response.text})
        assistant_call = []
        for i, call in enumerate(response.tool_calls):
            assistant_call.append({
                "id": f"call_{call_uid}",
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                },
            })
            call_uid += 1
        self.messages.append({
            "role": "assistant",
            "content": response.text,
            "tool_calls": assistant_call,
        })
        for i, call in enumerate(response.tool_calls):
            tool_id = f"call_{call_uid - len(response.tool_calls) + i}"
            if on_event:
                on_event("tool_call", {"name": call["name"], "arguments": call["arguments"]})
            tool_result = self.pipeline(call, self.context_for_tool())
            result.tool_results.append(tool_result)
            self._tool_calls.append({"name": call["name"], "arguments": call["arguments"]})
            if on_event:
                on_event("tool_output", {"name": call["name"], "output": tool_result.output, "error": tool_result.error, "status": tool_result.status})
            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": call["name"],
                "content": json.dumps(self._result_to_dict(tool_result), ensure_ascii=False),
            })
            norm = self._result_to_dict(tool_result)
            failed = norm.get("status") != "success" or bool(norm.get("error"))
            if failed:
                if call["name"] == fail_tool:
                    fail_seq += 1
                else:
                    fail_seq = 1
                    fail_tool = call["name"]
                max_fail_seq = max(max_fail_seq, fail_seq)
                if fail_seq >= self.config.failure_budget:
                    final = f"连续失败 {fail_seq} 次（工具 {fail_tool}），超过失败预算 {self.config.failure_budget}，停止重试。"
                    self.messages.append({"role": "assistant", "content": final})
                    result.text = final
                    if on_event:
                        on_event("token", {"content": final})
                    return self._finish(result, self.messages, max_fail_seq)
            else:
                fail_seq = 0
                fail_tool = None
    final = f"达到步数上限 {self.config.max_steps}，任务终止，未挂死。"
    self.messages.append({"role": "assistant", "content": final})
    result.text = final
    if on_event:
        on_event("token", {"content": final})
    return self._finish(result, self.messages, max_fail_seq)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest harness/tests/test_agent_core.py::test_chat_preserves_context -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests**

Run: `pytest harness/tests/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add harness/agent.py harness/tests/test_agent_core.py
git commit -m "feat: add chat() method for multi-turn conversation"
```

---

### Task 3: Create `StreamAgent` wrapper

**Files:**
- Create: `harness/webui/__init__.py`
- Create: `harness/webui/stream_agent.py`
- Test: `harness/tests/test_webui_stream_agent.py`

**Interfaces:**
- Consumes: `Config` (from `harness.config`), `Agent` (from `harness.agent`)
- Produces: `StreamAgent(config: Config) -> StreamAgent` with `async chat(message: str, push: Callable)`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from harness.config import Config
from harness.webui.stream_agent import StreamAgent


@pytest.mark.asyncio
async def test_stream_agent_echo(tmp_path):
    """使用 FakeLLM 验证 StreamAgent 能流式推送事件。"""
    cfg = Config(workspace=tmp_path, tool_timeout=5)
    agent = StreamAgent(cfg)
    # Override agent with FakeLLM-driven one for testing
    from harness.fake_llm import FakeLLM, FakeTurn
    from harness.agent import Agent
    from harness.hooks import HookBus
    from harness.policy import Policy
    from harness.registry import make_registry
    from harness.sandbox import LocalSandbox
    from harness.state import StateMachine
    from harness.tools.bash import spec as bash_spec
    sb = LocalSandbox()
    reg = make_registry([bash_spec()])
    llm = FakeLLM([FakeTurn(text="测试回复")])
    agent.agent = Agent(llm, reg, sb, HookBus(), Policy(), StateMachine(), None, cfg)
    events = []
    async def push(event):
        events.append(event)
    result = await agent.chat("你好", push)
    assert result.text == "测试回复"
    assert len(events) > 0
    assert any(e.get("type") == "token" for e in events)
    assert any(e.get("type") == "done" for e in events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest harness/tests/test_webui_stream_agent.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'harness.webui'"

- [ ] **Step 3: Create `__init__.py`**

```python
# empty
```

- [ ] **Step 4: Create `stream_agent.py`**

```python
from __future__ import annotations

from typing import Any, Callable, Coroutine

from harness.agent import Agent
from harness.config import Config
from harness.credentials import CredentialStore
from harness.hooks import HookBus
from harness.llm import OpenAILLM
from harness.memory import MemoryStore
from harness.mcp import load_mcp_servers
from harness.policy import Policy
from harness.registry import Tool, make_registry
from harness.sandbox import DockerSandbox, DockerUnavailableError, LocalSandbox
from harness.state import StateMachine
from harness.tools.ask import spec as ask_spec
from harness.tools.bash import spec as bash_spec
from harness.tools.files import spec as files_spec
from harness.tools.memory import specs as memory_specs
from harness.tools.notes import spec as notes_spec
from harness.tools.search import spec as search_spec
from harness.tools.skills import specs as skills_specs
from harness.tools.subagent import spec as subagent_spec
from harness.tools.web import spec as web_spec


class StreamAgent:
    """WebSocket 会话的 Agent 包装器，支持多轮对话和流式推送。"""

    def __init__(self, config: Config):
        self.config = config
        self.agent = self._make_agent(config)

    def _make_agent(self, config: Config) -> Agent:
        store = CredentialStore()
        api_key = store.get()
        if api_key:
            llm = OpenAILLM(api_key=api_key, base_url=config.base_url, model=config.model)
        else:
            from harness.fake_llm import FakeLLM, FakeTurn
            llm = FakeLLM([FakeTurn(text="未配置 API Key，请先在设置中配置。")])
        sandbox = self._build_sandbox(config)
        hooks = HookBus(transcript_dir=None)
        policy = Policy()
        state = StateMachine()
        memory = None
        if hasattr(config, 'workspace'):
            from pathlib import Path
            mem_dir = Path(config.workspace) / "memory"
            if mem_dir.is_dir():
                memory = MemoryStore(mem_dir, top_k=config.memory_top_k)
                memory.load()
        specs = [
            bash_spec(),
            web_spec(),
            ask_spec(),
            subagent_spec(),
            *files_spec(),
            *search_spec(),
            *notes_spec(),
            *([] if memory is None else memory_specs(memory)),
            *([] if not hasattr(config, 'workspace') else skills_specs(Path(config.workspace) / "skills")),
        ]
        registry = make_registry([self._to_tool(s) for s in specs])
        try:
            load_mcp_servers(config.mcp_servers, registry, sandbox, config)
        except Exception:
            pass
        return Agent(
            llm, registry, sandbox, hooks, policy, state, memory, config,
            ask_callback=None,
            on_text=None,
        )

    def _build_sandbox(self, config: Config):
        if config.sandbox_backend == "docker":
            try:
                return DockerSandbox(
                    workspace=config.workspace,
                    network_enabled=config.network_enabled,
                    max_output_bytes=config.max_output_bytes,
                )
            except Exception:
                pass
        return LocalSandbox(
            network_enabled=config.network_enabled,
            max_output_bytes=config.max_output_bytes,
        )

    @staticmethod
    def _to_tool(spec: Any) -> Tool:
        if isinstance(spec, Tool):
            return spec
        parameters = getattr(spec, "parameters", None)
        if parameters is None:
            parameters = getattr(spec, "schema", {"type": "object", "properties": {}, "required": []})
        return Tool(
            name=spec.name,
            description=spec.description,
            parameters=parameters,
            requires_approval=getattr(spec, "requires_approval", False),
            needs_sandbox=getattr(spec, "needs_sandbox", False),
            uses_workspace=getattr(spec, "uses_workspace", False),
            handler=spec.handler,
        )

    async def chat(self, message: str, push: Callable[[dict], Coroutine[Any, Any, None]]):
        """处理用户消息，通过 push 协程逐条推送事件。"""
        events = []

        def on_event(event_type: str, data: dict):
            events.append({"type": event_type, **data})

        result = self.agent.chat(message, on_event=on_event)
        for event in events:
            await push(event)
        await push({"type": "done"})
        return result

    async def stop(self):
        """停止当前生成（Agent 不支持中断，标记后 chat 返回）。"""
        pass
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest harness/tests/test_webui_stream_agent.py -v`
Expected: PASS

- [ ] **Step 6: Run all existing tests**

Run: `pytest harness/tests/ -q`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add harness/webui/__init__.py harness/webui/stream_agent.py harness/tests/test_webui_stream_agent.py
git commit -m "feat: add StreamAgent wrapper for WebSocket streaming"
```

---

### Task 4: Create FastAPI WebSocket server

**Files:**
- Create: `harness/webui/server.py`
- Test: `harness/tests/test_webui_server.py`

**Interfaces:**
- Consumes: `StreamAgent` from Task 3
- Produces: FastAPI app with WebSocket endpoint at `/ws` and REST endpoints at `/api/*`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from harness.webui.server import app


@pytest.mark.asyncio
async def test_server_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest harness/tests/test_webui_server.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'harness.webui.server'"

- [ ] **Step 3: Create `server.py`**

```python
from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from harness.config import Config
from harness.webui.stream_agent import StreamAgent

app = FastAPI(title="Coding Agent WebUI")

# In-memory session store
_sessions: dict[str, StreamAgent] = {}
_config = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/files")
async def list_files(path: str = "."):
    config = get_config()
    base = Path(config.workspace).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return JSONResponse({"error": "path outside workspace"}, status_code=403)
    if not target.is_dir():
        return JSONResponse({"error": "not a directory"}, status_code=400)
    entries = []
    for entry in sorted(target.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "path": str(entry.relative_to(base)),
        })
    return {"entries": entries, "path": path}


@app.get("/api/files/read")
async def read_file(path: str = Query(...)):
    config = get_config()
    base = Path(config.workspace).resolve()
    target = (base / path).resolve()
    if not str(target).startswith(str(base)):
        return JSONResponse({"error": "path outside workspace"}, status_code=403)
    if not target.is_file():
        return JSONResponse({"error": "not a file"}, status_code=400)
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return {"path": path, "content": content}


@app.get("/api/config")
async def get_config_endpoint():
    cfg = get_config()
    return {
        "model": cfg.model,
        "base_url": cfg.base_url,
        "max_steps": cfg.max_steps,
        "sandbox_backend": cfg.sandbox_backend,
        "workspace": str(cfg.workspace),
    }


@app.post("/api/config")
async def update_config(data: dict):
    cfg = get_config()
    if "model" in data:
        cfg.model = data["model"]
    if "base_url" in data:
        cfg.base_url = data["base_url"]
    if "max_steps" in data:
        cfg.max_steps = int(data["max_steps"])
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    config = get_config()
    agent = StreamAgent(config)
    session_id = id(agent)
    _sessions[session_id] = agent
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "chat":
                async def push(event: dict):
                    await websocket.send_text(json.dumps(event, ensure_ascii=False))
                await agent.chat(msg["content"], push)
            elif msg.get("type") == "stop":
                await agent.stop()
    except WebSocketDisconnect:
        pass
    finally:
        _sessions.pop(session_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest harness/tests/test_webui_server.py -v`
Expected: PASS

- [ ] **Step 5: Run all existing tests**

Run: `pytest harness/tests/ -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add harness/webui/server.py harness/tests/test_webui_server.py
git commit -m "feat: add FastAPI WebSocket server"
```

---

### Task 5: Create frontend HTML SPA

**Files:**
- Create: `harness/webui/static/index.html`
- (No test — frontend is verified by visual inspection)

**Interfaces:**
- Consumes: WebSocket at `ws://{host}:{port}/ws`, REST at `http://{host}:{port}/api/*`
- Produces: Self-contained single HTML file

- [ ] **Step 1: Create `index.html`**

The frontend is a single self-contained HTML file (~600 lines) with:

**Layout:**
- 256px collapsible sidebar (left) + main content area (right)
- Sidebar: new chat button, conversation list, file browser, settings link
- Main: message stream, bottom input bar

**Core features:**
1. WebSocket connection management (auto-reconnect on disconnect)
2. Message rendering: user messages right-aligned, LLM replies left-aligned with markdown
3. Real-time streaming: append tokens as they arrive
4. Tool call cards: collapsible, colored left border (bash=green, file=blue, web=purple, other=gray)
5. Stop button: replaces send button during generation
6. File browser: sidebar mode with tree view, click to preview
7. Settings modal: model, API key, sandbox mode
8. Dark theme (default) + light theme toggle

**Visual style:**
- Dark: `#1a1b1e` background, `#25262b` sidebar, `#2c2e33` cards
- Light: `#ffffff` background, `#f8f9fa` sidebar, `#f1f3f5` cards
- Accent: `#4c9aff` (blue)
- Font: system UI font, JetBrains Mono / monospace for code
- User messages: right-aligned, `#2c2e33` (dark) / `#e9ecef` (light) background
- Tool cards: left border 3px colored, collapsible with `▶`/`▼` toggle

**JavaScript dependencies (loaded from CDN):**
- highlight.js (code syntax highlighting)
- marked (markdown rendering) — optional, can use simple custom renderer

**Key states:**
- Disconnected: show "连接断开" banner, auto-reconnect
- Connecting: show spinner
- Streaming: input disabled, send button becomes stop button
- Error: show error message in chat, re-enable input

- [ ] **Step 2: Create the file**

Write the complete `harness/webui/static/index.html` file with all CSS, HTML, and JS inline.

- [ ] **Step 3: Commit**

```bash
git add harness/webui/static/index.html
git commit -m "feat: add WebUI frontend SPA"
```

---

### Task 6: Add `--web` CLI flag to `main.py`

**Files:**
- Modify: `harness/main.py`

**Interfaces:**
- Consumes: `argparse` for `--web` flag
- Produces: `cah --web` starts the FastAPI server

- [ ] **Step 1: Write the failing test**

```python
def test_web_flag_parsing():
    from harness.main import main
    # Just verify the arg parser accepts --web without error
    import sys
    old_argv = sys.argv
    try:
        sys.argv = ["cah", "--web", "--port", "18756"]
        # Should not raise
        main()
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
```

- [ ] **Step 2: Modify `main()` to accept `--web` flag**

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cah", description="Coding Agent Harness REPL")
    parser.add_argument("--config", "-c", type=Path, default=None, help="TOML 配置文件路径")
    parser.add_argument("--web", action="store_true", help="启动 WebUI 服务器")
    parser.add_argument("--port", type=int, default=8756, help="WebUI 端口（默认 8756）")
    args = parser.parse_args(argv)
    if args.web:
        return run_web(args.port, args.config)
    return run_repl(Config.load(args.config))


def run_web(port: int, config_path: Path | None) -> int:
    """启动 WebUI 服务器。"""
    import uvicorn
    from harness.webui.server import app
    print(f"WebUI 服务器启动于 http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
    return 0
```

- [ ] **Step 3: Run tests to verify**

Run: `pytest harness/tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add harness/main.py
git commit -m "feat: add --web flag to CLI"
```

---

### Task 7: Update `pyproject.toml` dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `pyproject.toml`**

```toml
dependencies = [
    "openai",
    "requests",
    "mcp",
    "keyring",
    "httpx",
    "fastapi",
    "uvicorn",
    "websockets",
    "python-multipart",
]
```

- [ ] **Step 2: Install new dependencies**

```bash
pip install fastapi uvicorn websockets python-multipart
```

- [ ] **Step 3: Run all tests**

Run: `pytest harness/tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add WebUI dependencies (fastapi, uvicorn, websockets)"
```
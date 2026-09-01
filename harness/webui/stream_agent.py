from __future__ import annotations

import asyncio
import threading
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
        self._ask_event: threading.Event | None = None
        self._ask_answer: str = ""
        self._push: Callable[[dict], Coroutine[Any, Any, None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
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
            ask_callback=self._ask_callback,
            on_text=None,
        )

    def _ask_callback(self, question: str, options: list[str]) -> str:
        """从线程池中调用：发送 ask 事件给前端，阻塞等待响应。"""
        self._ask_event = threading.Event()
        self._ask_answer = ""
        if self._loop is not None and self._push is not None:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._push({"type": "ask", "question": question, "options": options}),
                    self._loop,
                )
            except BaseException:
                pass
        self._ask_event.wait(timeout=300)
        return self._ask_answer or "n"

    def handle_ask_response(self, answer: str) -> None:
        """由 WebSocket 消息处理器调用，释放 ask_callback 的阻塞。"""
        self._ask_answer = answer
        if self._ask_event is not None:
            self._ask_event.set()

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
        self._loop = asyncio.get_running_loop()
        self._push = push

        def on_event(event_type: str, data: dict):
            try:
                asyncio.run_coroutine_threadsafe(
                    push({"type": event_type, **data}), self._loop
                )
            except BaseException:
                pass

        result = await asyncio.to_thread(self.agent.chat, message, on_event=on_event)
        await push({"type": "done"})
        return result

    async def stop(self):
        """停止当前生成（Agent 不支持中断，标记后 chat 返回）。"""
        pass
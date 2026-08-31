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
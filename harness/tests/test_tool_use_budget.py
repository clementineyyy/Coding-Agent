from harness.agent import Agent
from harness.config import Config
from harness.fake_llm import FakeLLM, FakeTurn
from harness.hooks import HookBus
from harness.policy import Policy
from harness.registry import make_registry
from harness.sandbox import LocalSandbox
from harness.state import StateMachine
from harness.tools.bash import spec as bash_spec


def make_agent(tmp_path, turns, **cfg_kw):
    cfg = Config(workspace=tmp_path, tool_timeout=5, **cfg_kw)
    reg = make_registry([bash_spec()])
    llm = FakeLLM(turns)
    return Agent(llm, reg, LocalSandbox(), HookBus(), Policy(), StateMachine(), None, cfg)


def test_narrate_then_nudge_then_call_tool(tmp_path):
    a = make_agent(
        tmp_path,
        [
            FakeTurn(text="计划：我会用 bash 查找程序。"),
            FakeTurn(tool_calls=[{"name": "bash", "arguments": {"command": "echo hi"}}]),
            FakeTurn(text="搞定了"),
        ],
    )
    r = a.run("找到 MySQL 位置并创建项目")
    assert r.steps_used == 3
    assert any(t.status == "success" for t in r.tool_results)
    assert "搞定了" in r.text
    sys_msgs = [m["content"] for m in a.messages if m["role"] == "system"]
    assert any("工具提示" in m or "还没有调用任何工具" in m for m in sys_msgs)


def test_narration_budget_exhausted_accepts_text(tmp_path):
    a = make_agent(
        tmp_path,
        [FakeTurn(text="第一段纯文本"), FakeTurn(text="第二段纯文本"), FakeTurn(text="最终回答")],
    )
    r = a.run("解释一下这个概念")
    assert r.steps_used == 3
    assert r.text == "最终回答"


def test_no_tool_marker_answers_immediately(tmp_path):
    a = make_agent(
        tmp_path,
        [FakeTurn(text="无需工具：这是一个概念问题。")],
    )
    r = a.run("解释一下这个概念")
    assert r.steps_used == 1
    assert "概念问题" in r.text


def test_tool_used_then_text_is_final_without_nudge(tmp_path):
    a = make_agent(
        tmp_path,
        [
            FakeTurn(tool_calls=[{"name": "bash", "arguments": {"command": "echo hi"}}]),
            FakeTurn(text="最终完成"),
        ],
    )
    r = a.run("执行一个命令")
    assert r.steps_used == 2
    assert r.text == "最终完成"
    sys_msgs = [m["content"] for m in a.messages if m["role"] == "system"]
    assert not any("工具提示" in m or "还没有调用任何工具" in m for m in sys_msgs)


def test_budget_zero_disables_nudge(tmp_path):
    a = make_agent(
        tmp_path,
        [FakeTurn(text="一句话回答")],
        tool_use_budget=0,
    )
    r = a.run("解释")
    assert r.steps_used == 1
    assert r.text == "一句话回答"
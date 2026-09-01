from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.agent import Agent
from harness.config import Config
from harness.fake_llm import FakeLLM, FakeTurn
from harness.feedback import FeedbackLoop, ValidationResult, Validator
from harness.hooks import HookBus
from harness.policy import Policy
from harness.registry import ToolResult, make_registry
from harness.sandbox import LocalSandbox
from harness.state import StateMachine
from harness.tools.bash import spec as bash_spec
from harness.tools.files import spec as files_specs


class TestValidator:
    def test_detect_nothing_in_empty_workspace(self, tmp_path):
        v = Validator(tmp_path, LocalSandbox())
        assert v.detect() == []

    def test_detect_pytest_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n" 'testpaths = ["tests"]\n',
            encoding="utf-8",
        )
        v = Validator(tmp_path, LocalSandbox())
        detected = v.detect()
        kinds = [d["kind"] for d in detected]
        assert "test" in kinds

    def test_detect_ruff_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ruff]\n",
            encoding="utf-8",
        )
        v = Validator(tmp_path, LocalSandbox())
        detected = v.detect()
        kinds = [d["kind"] for d in detected]
        assert "lint" in kinds

    def test_detect_mypy_from_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.mypy]\n",
            encoding="utf-8",
        )
        v = Validator(tmp_path, LocalSandbox())
        detected = v.detect()
        kinds = [d["kind"] for d in detected]
        assert "typecheck" in kinds

    def test_run_pytest_passes(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n" 'testpaths = ["."]\n',
            encoding="utf-8",
        )
        (tmp_path / "test_foo.py").write_text(
            "def test_foo(): assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        v = Validator(tmp_path, LocalSandbox())
        results = v.run_all(timeout=10)
        assert len(results) >= 1
        assert results[0].passed is True

    def test_run_pytest_fails(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n" 'testpaths = ["."]\n',
            encoding="utf-8",
        )
        (tmp_path / "test_fail.py").write_text(
            "def test_fail(): assert 1 + 1 == 3\n",
            encoding="utf-8",
        )
        v = Validator(tmp_path, LocalSandbox())
        results = v.run_all(timeout=10)
        assert len(results) >= 1
        assert results[0].passed is False

    def test_run_all_skips_missing_tools(self, tmp_path):
        v = Validator(tmp_path, LocalSandbox())
        results = v.run_all(timeout=5)
        assert results == []


class TestFeedbackLoop:
    def make_agent(self, tmp_path, turns):
        sb = LocalSandbox()
        cfg = Config(workspace=tmp_path, tool_timeout=5)
        specs = [bash_spec()] + files_specs()
        reg = make_registry(specs)
        return Agent(FakeLLM(turns), reg, sb, HookBus(), Policy(), StateMachine(), None, cfg)

    def test_should_validate_after_write_file(self, tmp_path):
        loop = FeedbackLoop(Validator(tmp_path, LocalSandbox()), None)
        assert loop._should_validate("write_file", {"path": "foo.py"}, ToolResult(status="success"))

    def test_should_not_validate_after_read_file(self, tmp_path):
        loop = FeedbackLoop(Validator(tmp_path, LocalSandbox()), None)
        assert not loop._should_validate("read_file", {"path": "foo.py"}, ToolResult(status="success"))

    def test_should_not_validate_after_failed_tool(self, tmp_path):
        loop = FeedbackLoop(Validator(tmp_path, LocalSandbox()), None)
        assert not loop._should_validate("write_file", {"path": "foo.py"}, ToolResult(status="error"))

    def test_respects_max_feedback_rounds(self, tmp_path):
        loop = FeedbackLoop(Validator(tmp_path, LocalSandbox()), None)
        loop._max_feedback_rounds = 1
        loop._feedback_round = 1
        assert not loop._should_validate("write_file", {"path": "foo.py"}, ToolResult(status="success"))

    def test_to_messages_format(self, tmp_path):
        loop = FeedbackLoop(Validator(tmp_path, LocalSandbox()), None)
        results = [ValidationResult(kind="test", command="pytest", passed=False, output="FAILED", duration_ms=100)]
        msgs = loop._to_messages(results)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "tool"
        assert "test" in msgs[0]["content"]
        assert "FAILED" in msgs[0]["content"]

    def test_feedback_loop_injects_into_chat(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n" 'testpaths = ["."]\n',
            encoding="utf-8",
        )
        (tmp_path / "test_foo.py").write_text(
            "def test_foo(): assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        turns = [
            FakeTurn(tool_calls=[{"name": "write_file", "arguments": {"path": "test_bar.py", "content": "def test_bar(): assert 2 + 2 == 4\n"}}]),
            FakeTurn(text="验证通过，所有测试通过"),
        ]
        a = self.make_agent(tmp_path, turns)
        a.feedback_loop = FeedbackLoop(Validator(tmp_path, a.sandbox), a)
        r = a.chat("写一个测试文件")
        tool_msgs = [m for m in r.messages if m.get("role") == "tool"]
        feedback_msgs = [m for m in tool_msgs if "feedback" in m.get("content", "").lower()]
        assert len(feedback_msgs) >= 1, "反馈消息应被注入"
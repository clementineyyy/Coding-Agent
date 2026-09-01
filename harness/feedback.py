from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from harness.agent import Agent
    from harness.registry import ToolResult
    from harness.sandbox import Sandbox


@dataclass
class ValidationResult:
    kind: str
    command: str
    passed: bool
    output: str
    duration_ms: int = 0


_DETECTORS: list[dict] = []


def _register(kind: str, config_key: str, command_template: str):
    _DETECTORS.append({
        "kind": kind,
        "config_key": config_key,
        "command_template": command_template,
    })


_register("test", "tool.pytest.ini_options", "python -m pytest -x --tb=short -q 2>&1")
_register("lint", "tool.ruff", "python -m ruff check . 2>&1")
_register("typecheck", "tool.mypy", "python -m mypy . 2>&1")


class Validator:
    def __init__(self, workspace: Path, sandbox: Sandbox):
        self.workspace = workspace
        self.sandbox = sandbox

    def detect(self) -> list[dict]:
        pyproject = self.workspace / "pyproject.toml"
        if not pyproject.exists():
            return []
        text = pyproject.read_text(encoding="utf-8")
        detected = []
        for d in _DETECTORS:
            if d["config_key"] in text:
                detected.append(dict(d))
        return detected

    def run_all(self, timeout: int = 30) -> list[ValidationResult]:
        detected = self.detect()
        if not detected:
            return []
        results = []
        for d in detected:
            start = time.monotonic()
            cmd = f"cd /d {self.workspace} && {d['command_template']}" if os.name == "nt" else f"cd {self.workspace} && {d['command_template']}"
            r = self.sandbox.run(cmd, timeout)
            elapsed = int((time.monotonic() - start) * 1000)
            results.append(ValidationResult(
                kind=d["kind"],
                command=d["command_template"],
                passed=r.exit_code == 0,
                output=(r.stdout or "") + (r.stderr or ""),
                duration_ms=elapsed,
            ))
        return results


class FeedbackLoop:
    def __init__(self, validator: Validator, agent: Agent | None):
        self.validator = validator
        self.agent = agent
        self._max_feedback_rounds = 3
        self._feedback_round = 0

    def _should_validate(self, tool_name: str, args: dict, result: ToolResult) -> bool:
        if self._feedback_round >= self._max_feedback_rounds:
            return False
        if result.status != "success":
            return False
        if tool_name == "write_file":
            return True
        if tool_name == "bash":
            return True
        return False

    def _to_messages(self, results: list[ValidationResult]) -> list[dict]:
        msgs = []
        for r in results:
            status = "passed" if r.passed else "failed"
            content = json.dumps({
                "type": "feedback",
                "kind": r.kind,
                "status": status,
                "command": r.command,
                "output": r.output,
                "duration_ms": r.duration_ms,
            }, ensure_ascii=False)
            msgs.append({"role": "tool", "tool_call_id": "feedback", "name": "validation", "content": content})
        return msgs

    def after_tool(self, tool_name: str, args: dict, result: ToolResult) -> list[dict]:
        if not self._should_validate(tool_name, args, result):
            return []
        self._feedback_round += 1
        results = self.validator.run_all()
        if not results:
            return []
        return self._to_messages(results)
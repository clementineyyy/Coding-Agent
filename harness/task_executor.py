from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from harness.registry import Context, ToolResult

_FILE_EXT = (
    r"(?:py|js|ts|jsx|tsx|java|go|rs|rb|php|c|h|cpp|hpp|cs|kt|swift|"
    r"sh|zsh|ps1|sql|json|yaml|yml|toml|md|html|css|txt|xml)"
)
_FILE_RE = re.compile(
    r"(?<![\w.])[\w\u4e00-\u9fff\-]+(?:\.[\w\u4e00-\u9fff\-]+)*\."
    + _FILE_EXT
    + r"\b"
)
_BLOCK_RE = re.compile(r"```([ \w+-]*)\s*\n?(.*?)```", re.DOTALL)

_COMMAND_LANGS = {"bash", "sh", "shell", "cmd", "powershell", "ps1", "console", "zsh"}

_EXT_FOR_LANG = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "jsx": ".jsx", "tsx": ".tsx",
    "java": ".java", "go": ".go", "golang": ".go",
    "rust": ".rs", "rs": ".rs", "ruby": ".rb", "php": ".php",
    "c": ".c", "cpp": ".cpp", "cs": ".cs", "kotlin": ".kt", "kt": ".kt",
    "swift": ".swift", "sql": ".sql", "sh": ".sh", "ps1": ".ps1",
}

_PROJECT_RE = re.compile(r"[\u4e00-\u9fff]{2,24}")
_LOOKUP_RE = re.compile(
    r"(?:查找|定位|搜索|在哪里|安装|where|which)\s*[:：.]?\s*([\w\u4e00-\u9fff\-]+)"
)


@dataclass
class Block:
    kind: str  # "code" | "command"
    lang: str
    content: str


@dataclass
class ExecReport:
    executed: list[dict] = field(default_factory=list)
    files_written: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)


def extract_targets(task: str) -> list[str]:
    seen: list[str] = []
    for m in _FILE_RE.finditer(task):
        raw = m.group(0).strip("` '\"")
        if raw and raw not in seen:
            seen.append(raw)
    return seen


def extract_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    for m in _BLOCK_RE.finditer(text):
        lang = (m.group(1) or "").strip().lower()
        content = m.group(2).strip("\n")
        if not content:
            continue
        kind = "command" if lang in _COMMAND_LANGS else "code"
        blocks.append(Block(kind=kind, lang=lang, content=content))
    return blocks


_VERB_PREFIX_RE = re.compile(
    r"^(?:谢谢|请|帮我|请你|我要|请帮我|麻烦你|麻烦)?\s*"
    r"(?:创建|生成|新建|编写|编写|写|开发|搭建|实现|构建|做|初始化|建立)\s*"
)


def fallback_filename(lang: str, task: str) -> str:
    base = "output"
    stripped = _VERB_PREFIX_RE.sub("", task)
    m = _PROJECT_RE.search(stripped)
    if m:
        base = m.group(0)
    if base.endswith("项目") and len(base) > 2:
        base = base[:-2]
    elif base.endswith("的") and len(base) > 2:
        base = base[:-1]
    if not base or base == "output":
        ascii_m = re.search(r"[A-Za-z_][A-Za-z0-9_]{1,24}", task)
        if ascii_m:
            base = ascii_m.group(0)
    ext = _EXT_FOR_LANG.get(lang or "python", ".py")
    return base + ext


def _lookup_token(task: str) -> str | None:
    m = _LOOKUP_RE.search(task)
    return m.group(1) if m else None


def _pick_filename(block_lang: str, task: str, targets: list[str]) -> str:
    if targets:
        if len(targets) == 1:
            return targets[0]
        ext = _EXT_FOR_LANG.get(block_lang)
        if ext:
            for t in targets:
                if t.endswith(ext):
                    return t
        return targets[0]
    return fallback_filename(block_lang, task)


class TaskExecutor:
    """确定性执行器：把模型文本中的代码块 / 命令块真实落地执行，不依赖模型是否调用工具。"""

    def __init__(self, agent: Any):
        self.agent = agent
        self.ctx: Context = agent.context_for_tool()

    def _run(self, name: str, args: dict) -> ToolResult:
        return self.agent.pipeline({"name": name, "arguments": args}, self.ctx)

    def execute(self, task: str, texts: list[str]) -> ExecReport:
        report = ExecReport()
        targets = extract_targets(task)
        blocks: list[Block] = []
        for t in texts:
            blocks.extend(extract_blocks(t))

        for b in blocks:
            if b.kind == "code":
                fname = _pick_filename(b.lang, task, targets)
                res = self._run("write_file", {"path": fname, "content": b.content})
                report.executed.append({"name": "write_file", "arguments": {"path": fname}})
                report.results.append(res)
                if res.status == "success":
                    report.files_written.append(fname)
                else:
                    report.skipped.append(f"write_file {fname}: {res.error}")
            elif b.kind == "command":
                res = self._run("bash", {"command": b.content})
                report.executed.append({"name": "bash", "arguments": {"command": b.content}})
                report.results.append(res)
                if res.status == "success":
                    report.commands_run.append(b.content)
                else:
                    report.skipped.append(f"bash: {res.error}")

        if not report.files_written and not report.commands_run:
            token = _lookup_token(task)
            if token:
                for probe in (f"where {token}", f"which {token}"):
                    res = self._run("bash", {"command": probe})
                    report.executed.append({"name": "bash", "arguments": {"command": probe}})
                    report.results.append(res)
                    if res.status == "success":
                        report.commands_run.append(probe)
                        break
        return report
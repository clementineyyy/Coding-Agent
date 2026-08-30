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
    "html": ".html", "htm": ".html", "css": ".css",
}

_WEB_HINTS = (
    "网页", "网站", "web项目", "web应用", "web端", "前端", "后端",
    "flask", "fastapi", "接口", "页面",
)
_STOP_TOKENS = {
    "flask", "fastapi", "html", "css", "javascript", "python",
    "vue", "react", "mysql", "sqlite", "crud", "api", "the", "and",
}

_DOMAIN_RULES = (
    ("学生管理系统", "student_management"),
    ("图书管理系统", "library_management"),
    ("库存管理系统", "inventory_management"),
    ("订单管理系统", "order_management"),
    ("工资管理系统", "payroll_management"),
    ("人事管理系统", "hr_management"),
    ("员工管理系统", "employee_management"),
    ("成绩管理系统", "grade_management"),
    ("客户管理系统", "customer_management"),
    ("商品管理系统", "product_management"),
    ("会议管理系统", "meeting_management"),
    ("课程管理系统", "course_management"),
    ("博客系统", "blog_system"),
    ("学生管理", "student_management"),
    ("图书管理", "library_management"),
    ("库存管理", "inventory_management"),
    ("订单管理", "order_management"),
    ("工资管理", "payroll_management"),
    ("人事管理", "hr_management"),
    ("员工管理", "employee_management"),
    ("成绩管理", "grade_management"),
    ("考勤管理", "attendance_management"),
    ("客户管理", "customer_management"),
    ("商品管理", "product_management"),
    ("会议管理", "meeting_management"),
    ("课程管理", "course_management"),
    ("记账", "bookkeeping"),
    ("任务清单", "todo_list"),
    ("待办", "todo"),
    ("计算器", "calculator"),
    ("博客", "blog"),
    ("商城", "shop"),
    ("电商", "ecommerce"),
)

_UNDERSCORE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,}\w*")
_LOOKUP_RE = re.compile(
    r"(?:查找|定位|搜索|在哪里|安装|where|which)\s*[:：.]?\s*([\w\u4e00-\u9fff\-]+)"
)

_FLASK_SKELETON = (
    "from flask import Flask, render_template\n"
    "app = Flask(__name__)\n\n"
    "@app.route('/')\n"
    "def index():\n"
    "    return render_template('index.html')\n\n"
    "if __name__ == '__main__':\n"
    "    app.run(debug=True)\n"
)
_INDEX_SKELETON = "<!doctype html>\n<html>\n<head><title>Web App</title></head>\n<body><h1>Web App</h1></body>\n</html>\n"

_WEB_FILE_FOR_LANG = {
    "python": "app.py", "py": "app.py",
    "html": "templates/index.html", "htm": "templates/index.html",
    "css": "static/style.css",
    "javascript": "static/script.js", "js": "static/script.js",
}


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


def is_web(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in _WEB_HINTS)


def _english_slug(texts: list[str]) -> str | None:
    joined = "\n".join(texts)
    for pattern, name in _DOMAIN_RULES:
        if pattern in joined:
            return name
    for token in re.findall(r"[A-Za-z]\w*", joined):
        token = token.rstrip("_")
        if not token or token.lower() in _STOP_TOKENS:
            continue
        if "_" in token or token.lower().endswith("web"):
            return token
    return None


def fallback_filename(lang: str, task: str, texts: list[str] | None = None) -> str:
    base = _english_slug(texts or [task]) or "main"
    ext = _EXT_FOR_LANG.get(lang or "python", ".py")
    return base + ext


def web_dir(texts: list[str]) -> str:
    base = _english_slug(texts) or "web_app"
    if base == "web_app" or base.endswith("_web") or base.endswith("web"):
        return base
    return base + "_web"


def _lookup_token(task: str) -> str | None:
    m = _LOOKUP_RE.search(task)
    return m.group(1) if m else None


def _filename_for_block(block: Block, task: str, texts: list[str], targets: list[str]) -> str:
    if targets:
        if len(targets) == 1:
            return targets[0]
        ext = _EXT_FOR_LANG.get(block.lang)
        if ext:
            for t in targets:
                if t.endswith(ext):
                    return t
        return targets[0]
    return fallback_filename(block.lang, task, texts)


class TaskExecutor:
    """确定性执行器：把模型文本中的代码块 / 命令块真实落地执行，不依赖模型是否调用工具。
    命名由代码规则生成英文单词（显式文件名 > 语义映射 > 英文兜底），Web 项目生成标准结构。"""

    def __init__(self, agent: Any):
        self.agent = agent
        self.ctx: Context = agent.context_for_tool()

    def _run(self, name: str, args: dict) -> ToolResult:
        return self.agent.pipeline({"name": name, "arguments": args}, self.ctx)

    def execute(self, task: str, texts: list[str]) -> ExecReport:
        report = ExecReport()
        all_texts = texts + [task]
        web = is_web("\n".join(all_texts))
        targets = []
        for t in all_texts:
            for name in extract_targets(t):
                if name not in targets:
                    targets.append(name)

        blocks: list[Block] = []
        for t in texts:
            blocks.extend(extract_blocks(t))

        if web:
            report = self._execute_web(task, all_texts, blocks, report)
        else:
            self._execute_simple(task, all_texts, targets, blocks, report)
        return report

    def _execute_web(self, task: str, all_texts: list[str], blocks: list[Block], report: ExecReport) -> ExecReport:
        d = web_dir(all_texts)
        has_python = any(b.lang in ("python", "py") for b in blocks if b.kind == "code")
        has_html = any(b.lang in ("html", "htm") for b in blocks if b.kind == "code")

        for b in blocks:
            if b.kind == "code":
                rel = _WEB_FILE_FOR_LANG.get(b.lang)
                if rel is None:
                    rel = fallback_filename(b.lang, task, all_texts)
                self._write(report, f"{d}/{rel}", b.content)
            elif b.kind == "command":
                self._run_command(report, b.content)

        if not has_python:
            self._write(report, f"{d}/app.py", _FLASK_SKELETON)
        if not has_html:
            self._write(report, f"{d}/templates/index.html", _INDEX_SKELETON)

        ws = self.ctx.config.workspace
        makedirs_cmd = f'python -c "import os; os.makedirs(r\'{ws}/{d}/static\', exist_ok=True)"'
        mk = self._run("bash", {"command": makedirs_cmd})
        report.executed.append({"name": "bash", "arguments": {"command": makedirs_cmd}})
        report.results.append(mk)
        if mk.status == "success":
            report.commands_run.append(makedirs_cmd)

        joined = "\n".join(all_texts)
        if any(k in joined for k in ("运行", "测试", "跑")) and not report.commands_run:
            compile_cmd = f"python -m py_compile {ws}/{d}/app.py"
            check = self._run("bash", {"command": compile_cmd})
            report.executed.append({"name": "bash", "arguments": {"command": compile_cmd}})
            report.results.append(check)
            if check.status == "success":
                report.commands_run.append(compile_cmd)
        return report

    def _execute_simple(self, task: str, all_texts: list[str], targets: list[str], blocks: list[Block], report: ExecReport) -> None:
        for b in blocks:
            if b.kind == "code":
                fname = _filename_for_block(b, task, all_texts, targets)
                self._write(report, fname, b.content)
            elif b.kind == "command":
                self._run_command(report, b.content)
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

    def _write(self, report: ExecReport, path: str, content: str) -> None:
        res = self._run("write_file", {"path": path, "content": content})
        report.executed.append({"name": "write_file", "arguments": {"path": path}})
        report.results.append(res)
        if res.status == "success":
            report.files_written.append(path)
        else:
            report.skipped.append(f"write_file {path}: {res.error}")

    def _run_command(self, report: ExecReport, command: str) -> None:
        res = self._run("bash", {"command": command})
        report.executed.append({"name": "bash", "arguments": {"command": command}})
        report.results.append(res)
        if res.status == "success":
            report.commands_run.append(command)
        else:
            report.skipped.append(f"bash: {res.error}")
from harness.agent import Agent
from harness.config import Config
from harness.fake_llm import FakeLLM, FakeTurn
from harness.hooks import HookBus
from harness.policy import Policy
from harness.registry import make_registry
from harness.sandbox import LocalSandbox
from harness.state import StateMachine
from harness.tools.bash import spec as bash_spec
from harness.tools.files import spec as files_spec
from harness.task_executor import extract_blocks, extract_targets, fallback_filename
from harness.task_executor import is_web, web_dir


def make_agent(tmp_path, turns, **cfg_kw):
    cfg = Config(workspace=tmp_path, tool_timeout=5, **cfg_kw)
    reg = make_registry([bash_spec(), *files_spec()])
    llm = FakeLLM(turns)
    return Agent(llm, reg, LocalSandbox(), HookBus(), Policy(), StateMachine(), None, cfg)


def test_extract_targets_finds_explicit_file():
    assert extract_targets("创建 app.py 和 config.json") == ["app.py", "config.json"]


def test_extract_targets_empty_for_no_file():
    assert extract_targets("解释一下什么是闭包") == []


def test_extract_blocks_splits_code_and_command():
    text = (
        "代码如下：\n```python\nprint('hi')\n```\n"
        "然后运行：\n```bash\npython app.py\n```\n"
    )
    blocks = extract_blocks(text)
    code = [b for b in blocks if b.kind == "code"]
    cmds = [b for b in blocks if b.kind == "command"]
    assert len(code) == 1 and code[0].content == "print('hi')"
    assert len(cmds) == 1 and cmds[0].content == "python app.py"


def test_fallback_filename_uses_english_slug():
    assert fallback_filename("python", "帮我创建学生管理系统") == "student_management.py"


def test_fallback_filename_never_cjk_prefix():
    name = fallback_filename("python", "需要你实现一个工具")
    assert name == "main.py"
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in name)


def test_is_web_and_web_dir():
    assert is_web("这是一个Web项目，用Flask做网页应用")
    assert web_dir(["帮我创建学生管理系统网页"]) == "student_management_web"


def test_executor_writes_model_code_and_runs_model_command(tmp_path):
    narration = (
        "我将创建学生管理系统：\n```python\nprint('欢迎使用学生管理系统')\n```\n"
        "然后运行：\n```bash\npython student_management.py\n```\n"
    )
    a = make_agent(tmp_path, [FakeTurn(text=narration)])
    r = a.run("帮我创建学生管理系统并运行")
    assert r.executed_by_executor is True
    target = tmp_path / "student_management.py"
    assert target.exists()
    assert "欢迎使用学生管理系统" in target.read_text(encoding="utf-8")
    assert any(c["name"] == "bash" for c in a._tool_calls)


def test_concept_question_no_execution(tmp_path):
    a = make_agent(tmp_path, [FakeTurn(text="无需工具：这是概念问题，解释如下：...")])
    r = a.run("解释一下什么是闭包")
    assert r.executed_by_executor is False
    assert not r.tool_results
    assert "概念" in r.text


def test_dangerous_command_in_model_text_is_denied(tmp_path):
    narration = "我准备删除系统文件：\n```bash\nrm -rf /\n```\n"
    a = make_agent(tmp_path, [FakeTurn(text=narration)])
    r = a.run("帮我执行文件操作")
    assert any(
        t.status == "error" and "guardrail denied" in (t.error or "")
        for t in r.tool_results
    )


def test_lookup_task_runs_search_command(tmp_path):
    a = make_agent(tmp_path, [FakeTurn(text="我会用 where 命令查找 mysql 的位置。")])
    r = a.run("帮我查找 mysql 在哪里安装了")
    assert r.executed_by_executor is True
    assert any(
        c["name"] == "bash" and "where" in c["arguments"].get("command", "")
        for c in a._tool_calls
    )
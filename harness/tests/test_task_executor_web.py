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


def make_agent(tmp_path, turns, **cfg_kw):
    cfg = Config(workspace=tmp_path, tool_timeout=5, **cfg_kw)
    reg = make_registry([bash_spec(), *files_spec()])
    llm = FakeLLM(turns)
    return Agent(llm, reg, LocalSandbox(), HookBus(), Policy(), StateMachine(), None, cfg)


def test_web_project_creates_structure_from_model_blocks(tmp_path):
    narration = (
        "项目结构：\nstudent_management_web/\n  app.py\n  templates/index.html\n  static/\n\n"
        "后端代码：\n```python\nfrom flask import Flask\napp = Flask(__name__)\n@app.route('/')\ndef index():\n    return 'hi'\n```\n"
        "前端页面：\n```html\n<h1>学生管理系统</h1>\n```\n"
    )
    a = make_agent(tmp_path, [FakeTurn(text=narration)])
    r = a.run("需要你实现，但是这是一个Web项目，而不是简单的一个py文件搞定")
    assert r.executed_by_executor is True
    app_file = tmp_path / "student_management_web" / "app.py"
    assert app_file.exists()
    assert "Flask" in app_file.read_text(encoding="utf-8")
    html = tmp_path / "student_management_web" / "templates" / "index.html"
    assert html.exists()
    assert "学生管理系统" in html.read_text(encoding="utf-8")
    assert (tmp_path / "student_management_web" / "static").is_dir()
    for p in tmp_path.rglob("*"):
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in p.name), p


def test_web_project_creates_runnable_skeleton_without_model_code(tmp_path):
    narration = "我会用 Flask 构建一个学生管理系统的网页应用。"
    a = make_agent(tmp_path, [FakeTurn(text=narration)])
    r = a.run("这是一个Web项目，帮我创建学生管理系统网站")
    assert r.executed_by_executor is True
    app_file = tmp_path / "student_management_web" / "app.py"
    assert app_file.exists()
    assert "Flask" in app_file.read_text(encoding="utf-8")
    html = tmp_path / "student_management_web" / "templates" / "index.html"
    assert html.exists()
    assert (tmp_path / "student_management_web" / "static").is_dir()


def test_model_python_block_lands_in_web_app_py(tmp_path):
    narration = (
        "我会把它做成网页。\n"
        "```python\nimport flask\nprint(flask.__version__)\n```\n"
    )
    a = make_agent(tmp_path, [FakeTurn(text=narration)])
    r = a.run("用Flask做一个网页项目")
    assert r.executed_by_executor is True
    app_file = tmp_path / "web_app" / "app.py"
    assert app_file.exists()
    assert "import flask" in app_file.read_text(encoding="utf-8")
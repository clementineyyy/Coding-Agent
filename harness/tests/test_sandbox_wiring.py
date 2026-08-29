"""沙箱接线：config.sandbox_backend / network_enabled → make_agent 选择 Docker 或 local；Docker 缺失回退。"""
from types import SimpleNamespace
from unittest.mock import patch

from harness.config import Config
from harness.sandbox import DockerSandbox, LocalSandbox


def test_config_defaults_docker_backend_and_network_enabled():
    c = Config()
    assert c.sandbox_backend == "docker"
    assert c.network_enabled is True


def test_config_toml_override_backend(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('sandbox_backend = "local"\nnetwork_enabled = false\n', encoding="utf-8")
    c = Config.load(p)
    assert c.sandbox_backend == "local"
    assert c.network_enabled is False


def test_make_agent_with_docker_available(tmp_path, monkeypatch):
    from harness.main import make_agent

    store = SimpleNamespace(get=lambda: "DUMMY-KEY")
    monkeypatch.setattr("harness.main.CredentialStore", lambda *a, **k: store)
    monkeypatch.setattr("harness.main._docker_available", lambda: True)
    agent = make_agent(Config(workspace=tmp_path, tool_timeout=5))
    assert isinstance(agent.sandbox, DockerSandbox)
    assert agent.sandbox.network_enabled is True


def test_make_agent_docker_disabled_sandbox_field(tmp_path, monkeypatch):
    from harness.main import make_agent

    store = SimpleNamespace(get=lambda: "DUMMY-KEY")
    monkeypatch.setattr("harness.main.CredentialStore", lambda *a, **k: store)
    monkeypatch.setattr("harness.main._docker_available", lambda: True)
    agent = make_agent(
        Config(workspace=tmp_path, tool_timeout=5, sandbox_backend="local")
    )
    assert isinstance(agent.sandbox, LocalSandbox)


def test_make_agent_uses_local_network_flag(tmp_path, monkeypatch):
    from harness.main import make_agent

    store = SimpleNamespace(get=lambda: "DUMMY-KEY")
    monkeypatch.setattr("harness.main.CredentialStore", lambda *a, **k: store)
    monkeypatch.setattr("harness.main._docker_available", lambda: False)
    agent = make_agent(
        Config(workspace=tmp_path, tool_timeout=5, sandbox_backend="docker",
               network_enabled=False)
    )
    assert isinstance(agent.sandbox, LocalSandbox)
    assert agent.sandbox.network_enabled is False


def test_make_agent_falls_back_local_when_docker_missing(tmp_path, monkeypatch, capsys):
    from harness.main import make_agent

    store = SimpleNamespace(get=lambda: "DUMMY-KEY")
    monkeypatch.setattr("harness.main.CredentialStore", lambda *a, **k: store)
    with patch("shutil.which", return_value=None):
        agent = make_agent(Config(workspace=tmp_path, tool_timeout=5))
    assert isinstance(agent.sandbox, LocalSandbox)
    out = capsys.readouterr().out
    assert "Docker" in out and "local" in out.lower()


def test_fetch_url_available_when_network_enabled(tmp_path, monkeypatch):
    from harness.main import make_agent

    store = SimpleNamespace(get=lambda: "DUMMY-KEY")
    monkeypatch.setattr("harness.main.CredentialStore", lambda *a, **k: store)
    monkeypatch.setattr("harness.main._docker_available", lambda: False)
    agent = make_agent(
        Config(workspace=tmp_path, tool_timeout=5, network_enabled=True)
    )
    assert "fetch_url" in agent.registry
    assert agent.sandbox.network_enabled is True


def test_docker_available_checks_cli_and_daemon(monkeypatch):
    from harness.main import _docker_available

    import subprocess

    with patch("shutil.which", return_value="docker"):
        with patch("subprocess.run") as m:
            m.return_value = SimpleNamespace(returncode=0)
            assert _docker_available() is True
            args = m.call_args.args[0]
            assert args[0] == "docker" and "info" in args


def test_docker_available_false_when_cli_missing(monkeypatch):
    from harness.main import _docker_available

    with patch("shutil.which", return_value=None):
        assert _docker_available() is False


def test_docker_available_false_when_daemon_down(monkeypatch):
    from harness.main import _docker_available

    with patch("shutil.which", return_value="docker"):
        with patch("subprocess.run") as m:
            m.return_value = SimpleNamespace(returncode=1)
            assert _docker_available() is False
import pytest

from agentbench.onboarding.build_agent_env.common import writer


def test_install_file_without_fchmod_support(tmp_path, monkeypatch):
    monkeypatch.delattr(writer.os, "fchmod", raising=False)

    installed = writer.install_file(tmp_path, "agent.toml", "value = 1\n")

    assert installed.read_text(encoding="utf-8") == "value = 1\n"
    assert not list(tmp_path.glob(".agent-build-*"))


def test_install_file_closes_temporary_before_cleanup(tmp_path, monkeypatch):
    def fail_permissions(file_descriptor, mode):
        raise OSError("permission setup failed")

    monkeypatch.setattr(writer.os, "fchmod", fail_permissions, raising=False)

    with pytest.raises(OSError, match="permission setup failed"):
        writer.install_file(tmp_path, "agent.toml", "value = 1\n")

    assert not (tmp_path / "agent.toml").exists()
    assert not list(tmp_path.glob(".agent-build-*"))


def test_install_file_preserves_an_existing_destination(tmp_path):
    destination = tmp_path / "agent.toml"
    destination.write_text("manual = true\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        writer.install_file(tmp_path, "agent.toml", "generated = true\n")

    assert destination.read_text(encoding="utf-8") == "manual = true\n"
    assert not list(tmp_path.glob(".agent-build-*"))

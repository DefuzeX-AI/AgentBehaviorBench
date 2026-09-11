from dataclasses import replace
import pytest
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.adapter.langgraph.loader import load_graph, LangGraphLoadError
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts import EnvironmentSecretResolver
from agentbench.runtime.docker.worker_build import worker_build_context


def test_outer_binding_cannot_escape_its_directory(offline_agent):
    (offline_agent.path / "bindings").mkdir()
    config = replace(LangGraphAdapterConfig.from_agent_dir(offline_agent.path), binding="../agent/sample.py:graph")
    with pytest.raises(LangGraphLoadError, match="escapes"):
        load_graph(config)


def test_build_excludes_secrets_and_local_venv(offline_agent, tmp_path):
    root = offline_agent.path
    (root / ".env").write_text("SECRET=private")
    (root / ".venv").mkdir()
    (root / ".venv/python").symlink_to("/usr/bin/python3")
    config = AgentContainerConfig.from_agent_dir(root, secret_resolver=EnvironmentSecretResolver({}))
    with worker_build_context(config) as (context, dockerfile):
        assert not (context / ".env").exists()
        assert not (context / ".venv").exists()
        assert (context / ".abb-runtime/agentbench/runtime/agentcontainer/worker.py").is_file()
    secret = tmp_path / "private.txt"
    secret.write_text("private")
    (root / "leak").symlink_to(secret)
    with pytest.raises(ValueError, match="symlinks"):
        with worker_build_context(config):
            pytest.fail("Unsafe build context accepted")

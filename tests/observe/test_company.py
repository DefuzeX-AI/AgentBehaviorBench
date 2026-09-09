import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest


def test_original_company_graph_with_controlled_http(tmp_path):
    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_google_genai")
    pytest.importorskip("tavily")
    repo = Path(__file__).resolve().parents[2]
    source = repo / "resources/agents/01-company-research-agent"
    root = tmp_path / "company"
    shutil.copytree(source, root, ignore=shutil.ignore_patterns("__pycache__", ".git", ".env*"))
    shutil.copy(Path(__file__).with_name("company_upstream.py"), root / "bindings/controlled_upstream.py")
    (root / "bindings/offline.py").write_text('from controlled_upstream import install\ninstall()\nfrom company import create_graph\n')
    manifest = (root / "agent.toml").read_text().replace('binding = "company.py:create_graph"', 'binding = "offline.py:create_graph"')
    (root / "agent.toml").write_text(manifest)
    output = tmp_path / "result"
    output.mkdir()
    request = tmp_path / "input.json"
    request.write_text(json.dumps({"schema": "abb.invocation.v1", "run_id": "company-offline", "agent_id": "company-research-agent",
                  "framework": "langgraph", "input": {"company": "测试公司", "company_url": "https://example.test",
                                                         "hq_location": "Toronto", "industry": "Software"}}))
    environ = dict(os.environ, OPENAI_API_KEY="offline", GEMINI_API_KEY="offline", TAVILY_API_KEY="offline",
                   PYTHONPATH=os.pathsep.join([str(repo), str(repo / "services/model-interceptor/src")]))
    result = subprocess.run([sys.executable, "-m", "agentbench.runtime.agentcontainer.worker", "--agent-root", str(root),
                             "--request", str(request), "--output", str(output)], env=environ, capture_output=True, text=True, timeout=60)
    saved = json.loads((output / "result.json").read_text())
    assert result.returncode == 0, (saved, result.stderr[-5000:])
    assert "OFFLINE REPORT" in saved["output"]
    events = [json.loads(line) for line in (output / "framework.jsonl").read_text().splitlines()]
    names = {r["data"].get("name") for r in events}
    assert {"grounding", "financial_analyst", "news_scanner", "industry_analyst", "company_analyst",
            "collector", "curator", "enricher", "briefing", "editor", "tavily.search", "tavily.crawl", "tavily.extract"} <= names
    start = next(r for r in events if r["event"] == "execution_start")
    assert start["data"]["input"]["company_url"] == "https://example.test"
    assert any(r["event"] == "native_event" for r in events)


@pytest.mark.skipif(os.getenv("ABB_DOCKER_TEST") != "1", reason="Opt-in actual Company Docker image")
def test_company_image_executes_original_graph_offline(tmp_path):
    from agentbench.runtime.agentcontainer.config import AgentContainerConfig
    from agentbench.runtime.contracts import EnvironmentSecretResolver
    from agentbench.runtime.docker.worker_build import worker_build_context
    from agentbench.runtime.docker.image_builder import DockerImageBuilder
    from agentbench.runtime.docker.policy import DockerPolicy
    repo = Path(__file__).resolve().parents[2]
    config = AgentContainerConfig.from_agent_dir(repo / "resources/agents/01-company-research-agent",
                                               secret_resolver=EnvironmentSecretResolver({"TAVILY_API_KEY": "offline"}))
    with worker_build_context(config) as (context, dockerfile):
        image = DockerImageBuilder().build(context=context, dockerfile=dockerfile, repository="company-research-agent")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    shutil.copy(Path(__file__).with_name("company_upstream.py"), fixtures)
    shutil.copytree(repo / "services/model-interceptor/src/defuzex_model_interceptor", fixtures / "defuzex_model_interceptor")
    (fixtures / "entry.py").write_text('''import asyncio
import sys
from pathlib import Path
from company_upstream import install
install()
from agentbench.runtime.agentcontainer.worker import execute
assert 'defuzex' not in sys.modules
assert not Path('/opt/agent/agent.toml').stat().st_mode & 2
raise SystemExit(asyncio.run(execute(Path('/opt/agent'), Path('/run/tests/input.json'), Path('/run/abb-output'))))
''')
    (fixtures / "input.json").write_text(json.dumps({"schema": "abb.invocation.v1", "run_id": "docker-company-offline",
                    "agent_id": "company-research-agent", "framework": "langgraph",
                    "input": {"company": "测试公司", "company_url": "https://example.test", "industry": "Software"}}))
    output = tmp_path / "output"
    output.mkdir()
    output.chmod(0o777)
    command = ["docker", "run", "--rm", "--network", "none", *DockerPolicy().run_arguments(),
               "--mount", f"type=bind,source={fixtures},target=/run/tests,readonly",
               "--mount", f"type=bind,source={output},target=/run/abb-output",
               "--env", "OPENAI_API_KEY=offline", "--env", "GEMINI_API_KEY=offline", "--env", "TAVILY_API_KEY=offline",
               image, "python", "/run/tests/entry.py"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=90)
    saved = json.loads((output / "result.json").read_text()) if (output / "result.json").exists() else {}
    assert process.returncode == 0, (saved, process.stderr[-5000:])
    assert "OFFLINE REPORT" in saved["output"]

"""Opt-in native report-chat acceptance using real container dependencies.

Run with ABB_NATIVE_CHAT_IMAGE set to a cached GPT Researcher image. External
model and NCBI transports are deterministic offline doubles; Agent research,
the original FastAPI application, report storage, embeddings and KUMA execute.
"""
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from agentbench.runtime.docker.policy import DockerPolicy


@pytest.mark.skipif(not os.getenv("ABB_NATIVE_CHAT_IMAGE"), reason="Opt-in cached GPT Researcher image")
def test_native_report_chat_owns_history_across_case_turns_and_cleans_up():
    repository = Path(__file__).resolve().parents[1]
    output = repository / "results/verification" / f"issue39-native-chat-{uuid4().hex}"
    output.mkdir(parents=True)
    image = os.environ["ABB_NATIVE_CHAT_IMAGE"]
    settings = json.loads((repository / "resources/agents/04-gpt-researcher/bindings/research.json").read_text())
    # Cached images may predate the new Docker ENV layer. Mirror its declared
    # native configuration while mounting the current binding/source below.
    native_environment = []
    for key in ("EMBEDDING", "EMBEDDING_KWARGS", "FAST_LLM", "SMART_LLM", "STRATEGIC_LLM", "RETRIEVER"):
        value = settings[key]
        native_environment.extend(["--env", key + "=" + (json.dumps(value) if isinstance(value, dict) else value)])
    command = ["docker", "run", "--rm", "--network", "none",
        *DockerPolicy().run_arguments(),
        "--user", "10001:10001", "--workdir", "/opt/agent",
        "--env", "PYTHONPATH=/opt/current-runtime:/opt/agent/agent",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "KUMA_API_KEY=", "--env", "DEFUZEX_API_KEY=", "--env", "TAVILY_API_KEY=",
        *native_environment,
        "--mount", f"type=bind,source={repository / 'agentbench'},target=/opt/current-runtime/agentbench,readonly",
        "--mount", f"type=bind,source={repository / 'resources/agents/04-gpt-researcher'},target=/opt/agent,readonly",
        "--mount", f"type=bind,source={repository / 'tests/agent_fixtures'},target=/checks,readonly",
        "--mount", f"type=bind,source={output},target=/artifacts",
        "--entrypoint", "python", image, "/checks/native_report_chat.py"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=240)
    (output / "container.log").write_text(process.stdout + process.stderr)
    assert process.returncode == 0, f"See {output / 'container.log'}"
    check = json.loads((output / "acceptance.json").read_text())
    assert check["status"] == "passed"
    assert check["network"] == "none"
    assert check["app_function_replacements"] == []
    assert check["local_embeddings"] is True
    assert check["overlapping_sessions"]["survivor_retained_memory"] is True
    assert len(check["cases"]) >= 2
    for case in check["cases"]:
        folder = output / case["name"]
        assert case["session_closed"] is True
        assert case["storage_removed"] is True
        assert (folder / "case.json").is_file()
        assert json.loads((folder / "judge/report.json").read_text())["status"] == "pass"
    print(f"Native GPT report-chat acceptance artifacts retained: {output}", flush=True)

import json
import os
import subprocess
import sys
import pytest


def worker(agent, tmp_path, number, context=None):
    output = tmp_path / f"output{number}"
    output.mkdir()
    request = tmp_path / f"request{number}.json"
    request.write_text(json.dumps({"schema": "abb.invocation.v1", "run_id": f"test{number}",
                                  "agent_id": agent.agent_id, "framework": agent.framework,
                                  "observation_context": context,
                                  "input": {"number": number, "text": '中文"\n原样'}}))
    result = subprocess.run([sys.executable, "-m", "agentbench.runtime.agentcontainer.worker",
                             "--agent-root", str(agent.path), "--request", str(request),
                             "--output", str(output)], capture_output=True, text=True, timeout=30)
    return result, output


def test_real_async_graph_in_child_process(offline_agent, tmp_path):
    process, directory = worker(offline_agent, tmp_path, 4)
    assert process.returncode == 0, process.stderr
    result = json.loads((directory / "result.json").read_text())
    assert result["output"] == '中文"\n原样:11'
    events = [json.loads(line) for line in (directory / "framework.jsonl").read_text().splitlines()]
    names = [event["data"].get("name") for event in events]
    assert "double" in names and "finish" in names
    assert any(event["data"].get("parent_span_id") for event in events)


def test_graph_failure_is_not_success(offline_agent, tmp_path):
    process, directory = worker(offline_agent, tmp_path, -1)
    assert process.returncode == 1
    result = json.loads((directory / "result.json").read_text())
    assert result["status"] == "failed" and "negative input" in result["error"]


def test_observation_identity_is_preserved_without_changing_agent_input(offline_agent, tmp_path):
    process, directory = worker(offline_agent, tmp_path, 5, {'case_id': 'case-other-sdk', 'input_id': 'input-z', 'invocation_id': 'cannot-override'})
    assert process.returncode == 0, process.stderr
    result = json.loads((directory / 'result.json').read_text())
    assert result['output'] == '中文"\n原样:13'
    assert result['input_id'] == 'input-z' and result['invocation_id'] == 'test5'
    events = [json.loads(line) for line in (directory / 'framework.jsonl').read_text().splitlines()]
    assert all(e['data']['case_id'] == 'case-other-sdk' and e['data']['input_id'] == 'input-z' and e['data']['invocation_id'] == 'test5' for e in events)
    if (directory / 'otel.jsonl').exists():
        spans = [json.loads(line)['data'] for line in (directory / 'otel.jsonl').read_text().splitlines()]
        assert all(s['attributes']['abb.input_id'] == 'input-z' and s['attributes']['abb.case_id'] == 'case-other-sdk' for s in spans)


@pytest.mark.skipif(os.getenv("ABB_DOCKER_TEST") != "1", reason="Opt-in real Docker build")
def test_real_docker_offline_execution_and_isolation(offline_agent, tmp_path):
    from agentbench.runtime.docker import DockerRuntime
    from agentbench.runtime.agentcontainer.adapter import ContainerAgentAdapter
    runtime = DockerRuntime(artifact_root=tmp_path / "artifacts", environ={"ABB_CONTAINER_TEST": "1"})
    adapter = ContainerAgentAdapter(offline_agent, runtime)
    try:
        first = adapter.invoke({"number": 4, "text": '中文"\n原样'})
        second = adapter.invoke({"number": 8, "text": "second"})
    finally:
        adapter.close()
    assert first.output == '中文"\n原样:11'
    assert second.output == "second:19"
    results = list((tmp_path / "artifacts").rglob("result.json"))
    assert len(results) == 2
    assert len({json.loads(p.read_text())["run_id"] for p in results}) == 2

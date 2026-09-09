import os
from pathlib import Path
import subprocess
import pytest


@pytest.mark.skipif(os.getenv("ABB_DOCKER_TEST") != "1", reason="Opt-in real Interceptor image")
def test_interceptor_image_protocol_pipeline(tmp_path):
    from agentbench.runtime.docker.image_builder import DockerImageBuilder
    repo = Path(__file__).resolve().parents[2]
    context = repo / "services/model-interceptor"
    image = DockerImageBuilder().build(context=context, dockerfile=context / "Dockerfile", repository="model-interceptor")
    checks = Path(__file__).with_name("interceptor_checks.py")
    result = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                             "--entrypoint", "python", "--mount", f"type=bind,source={checks},target=/checks.py,readonly",
                             image, "/checks.py"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    # Exercise Docker stdout -> host event parsing -> actual JSONL persistence.
    import json
    from agentbench.runtime.interception.trace import TraceEvent
    from agentbench.observe.store import TraceStore
    path = tmp_path / "network.jsonl"
    store = TraceStore(path, "large-wire-test", source="interceptor")
    for line in result.stdout.splitlines():
        event = TraceEvent.from_log_line(line)
        if event is not None:
            store.emit(event)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    large = next(e for e in events if e["event"] == "large_transport_test")
    assert large["data"]["raw_body"] == "完整输出" * 100000 + "[DONE]"

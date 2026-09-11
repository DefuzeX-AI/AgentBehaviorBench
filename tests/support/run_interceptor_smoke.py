"""Manual Docker smoke test for the full transparent interception runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import (
    ModelTargetConfig,
    StaticInterceptorImageProvider,
    StaticModelTargetProvider,
    TraceEvent,
)


@dataclass(frozen=True)
class Descriptor:
    framework: str
    path: Path


@dataclass
class CollectingSink:
    events: list[TraceEvent] = field(default_factory=list)

    def emit(self, event: TraceEvent) -> None:
        self.events.append(event)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    sink = CollectingSink()
    runtime = DockerRuntime(
        environ={"SMOKE_PROVIDER_KEY": "provider-test-secret"},
        interceptor_image_provider=StaticInterceptorImageProvider(
            "defuzex-agentbench/model-interceptor:manual"
        ),
        model_provider=StaticModelTargetProvider(
            ModelTargetConfig(
                provider_id="openrouter-smoke",
                target_plugin="openrouter",
                base_url="https://httpbingo.org/anything",
                model="openrouter-smoke-model",
                credential_env="SMOKE_PROVIDER_KEY",
            )
        ),
        trace_sink=sink,
    )
    descriptor = Descriptor(
        framework="fixture",
        path=root / "tests" / "fixtures" / "interceptor-agent",
    )
    with runtime.start(descriptor) as session:
        assert session.wait(timeout=30) == 0, session.stderr
        assert "Model request completed successfully" in session.stdout
        # The log follower may receive the last trace after the process exits.
        import time
        deadline = time.monotonic() + 5
        while not any(event.event == "llm_response" for event in sink.events):
            if time.monotonic() >= deadline:
                raise AssertionError("Interceptor response trace was not received")
            time.sleep(0.05)

    requests = [event for event in sink.events if event.event == "llm_request"]
    responses = [event for event in sink.events if event.event == "llm_response"]
    assert len(requests) == len(responses) == 1
    assert requests[0].data["call_id"] == responses[0].data["call_id"]
    assert requests[0].data["source_path"] == "/anything/source"
    assert requests[0].data["path"] == "/anything/chat/completions"
    assert requests[0].data["model"] == "openrouter-smoke-model"
    serialized = json.dumps([event.data for event in sink.events])
    assert "provider-test-secret" not in serialized
    assert "temporary-test-token" not in serialized
    print("transparent interceptor smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

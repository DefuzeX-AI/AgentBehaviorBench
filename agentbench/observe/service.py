"""Observe orchestration, independent of benchmark cases and evaluation SDKs."""
from pathlib import Path
from uuid import uuid4

from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.runtime.factory import RuntimeFactory
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.agentcontainer.config import runtime_type, execution_strategy
from .store import TraceStore, atomic_json, summarize


def observe(agent, value, *, output: Path, environ, timeout=None):
    if runtime_type(agent.path) != "docker" or execution_strategy(agent.path) != "oneshot":
        raise ValueError("Observe currently requires runtime.type=docker and execution=oneshot; native services need an explicit observe caller")
    run_id = uuid4().hex
    directory = output.resolve() / run_id
    directory.mkdir(parents=True, mode=0o700)
    print(f"Run: {run_id}\nArtifacts: {directory}", flush=True)
    store = TraceStore(directory / "network.jsonl", run_id, source="interceptor")
    runtime = DockerRuntime(environ=environ, trace_sink=store, artifact_root=directory,
                            timeout_sec=timeout, run_id=run_id)
    adapter = RuntimeFactory(docker_builder=lambda: runtime).create_adapter(
        agent, adapter_factory=DEFAULT_ADAPTER_FACTORY)
    result = {"schema": "abb.observe.run.v1", "run_id": run_id, "agent_id": agent.agent_id,
              "status": "running", "input": value}
    atomic_json(directory / "run.json", result)
    try:
        adapter.load()
        invocation = adapter.invoke(value)
        result.update(status="succeeded", output=invocation.output)
        if isinstance(invocation.output, str):
            (directory / "report.md").write_text(invocation.output, encoding="utf-8")
    except BaseException as exc:
        result.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                      error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        try:
            adapter.close()
        finally:
            result["trace_summary"] = summarize(directory)
            if result["status"] == "succeeded" and (
                result["trace_summary"].get("framework:span_error", 0)
                or result["trace_summary"].get("framework:tool_incomplete", 0)
                or result["trace_summary"].get("interceptor:llm_error", 0)
            ):
                result["status"] = "degraded"
                result["warning"] = "Report returned, but observed operations failed; inspect trace before accepting the run."
            atomic_json(directory / "run.json", result)
            print(f"Status: {result['status']}\nTrace: {result['trace_summary']}", flush=True)
    if result["status"] == "degraded":
        raise RuntimeError(result["warning"])
    return directory

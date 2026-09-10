"""One invocation inside an isolated process; never selects another runtime."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.observe.store import TraceStore, atomic_json
from agentbench.observe.correlation import model_correlation
from agentbench.runtime.interception import InterceptionConfig


def configure_trust():
    """Keep public CA roots for non-model HTTPS (e.g. real search)."""
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and Path(ca).is_file():
        import certifi
        bundle = Path("/tmp/abb-ca-bundle.pem")
        bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + Path(ca).read_bytes())
        for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"):
            os.environ[key] = str(bundle)


async def execute(root: Path, request: Path, output: Path, *, provider=None):
    envelope = json.loads(request.read_text(encoding="utf-8"))
    run_id = envelope["run_id"]
    if envelope.get("schema") != "abb.invocation.v1" or not isinstance(run_id, str):
        raise ValueError("Invalid invocation envelope")
    store = TraceStore(output / "framework.jsonl", envelope.get("session_id", run_id), source="framework")
    # Optional dependency: images with OTel emit a second, independent trace.
    try:
        from agentbench.observe.otel.session import ObservedStore
    except ModuleNotFoundError as exc:
        if not (exc.name or '').startswith('opentelemetry'):
            raise
        atomic_json(output / 'otel-status.json', {'status': 'unavailable', 'reason': 'OTel SDK not installed'})
    else:
        store = ObservedStore(store, run_id, provider=provider)
    adapter = None
    result = {"schema": "abb.result.v1", "run_id": run_id, "agent_id": envelope["agent_id"]}
    try:
        configure_trust()
        # Agent imports and later lazy imports live only in this worker process.
        sys.path[:0] = [str(root / "agent"), str(root / "agent" / "src")]
        descriptor = SimpleNamespace(path=root, framework=envelope["framework"])
        adapter = DEFAULT_ADAPTER_FACTORY.create(descriptor)
        config = dict(envelope.get("config") or {})
        if "callbacks" in config:
            raise ValueError("Host callbacks cannot cross a JSON process boundary")
        from agentbench.observe.observers import DEFAULT_OBSERVERS
        callbacks = DEFAULT_OBSERVERS.callbacks(descriptor.framework, store)
        if callbacks:
            config["callbacks"] = callbacks
        config.setdefault("configurable", {}).setdefault("thread_id", run_id)
        config.setdefault("metadata", {}).update(abb_run_id=run_id)
        store.record("execution_start", input=envelope["input"])
        adapter.load()
        interception = InterceptionConfig.from_agent_dir(root)
        hosts = [host for route in interception.routes for host in route.host_patterns] if interception else []
        with model_correlation(hosts):
            invocation = await adapter.ainvoke(envelope["input"], run_config=config)
        result.update(status="succeeded", output=invocation.output, raw_output=invocation.raw_output)
        store.record("execution_end", output=invocation.output)
    except BaseException as exc:
        result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        store.record("execution_error", error_type=type(exc).__name__, error=str(exc))
    finally:
        if adapter is not None:
            try:
                adapter.close()
            except Exception as exc:
                result.update(status="failed", error_type=type(exc).__name__, error=str(exc))
        atomic_json(output / "result.json", result)
        if hasattr(store, 'close'):
            store.close()
    return 0 if result["status"] == "succeeded" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-root", type=Path, default=Path("/opt/agent"))
    parser.add_argument("--request", type=Path, default=Path("/run/abb-input/request.json"))
    parser.add_argument("--output", type=Path, default=Path("/run/abb-output"))
    args = parser.parse_args()
    return asyncio.run(execute(args.agent_root.resolve(), args.request, args.output))


if __name__ == "__main__":
    raise SystemExit(main())

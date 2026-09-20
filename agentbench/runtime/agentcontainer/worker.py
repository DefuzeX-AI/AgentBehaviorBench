"""One invocation inside an isolated process; never selects another runtime."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from agentbench.observe.store import TraceStore, atomic_json
from agentbench.observe.correlation import model_correlation
from agentbench.runtime.interception import InterceptionConfig
from .session import AgentSession


def configure_trust():
    """Keep public CA roots for non-model HTTPS (e.g. real search)."""
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and Path(ca).is_file():
        import ssl
        try:
            import certifi
        except ModuleNotFoundError:
            # Node ACP images need not install Python HTTP clients. OpenSSL's
            # compiled-in path avoids the SSL_CERT_FILE override being merged
            # with itself instead of the system's public roots.
            roots = ssl.get_default_verify_paths().openssl_cafile
        else:
            roots = certifi.where()
        if not roots or not Path(roots).is_file():
            raise RuntimeError('Worker needs system CA certificates or certifi for model interception')
        bundle = Path("/tmp/abb-ca-bundle.pem")
        bundle.write_bytes(Path(roots).read_bytes() + b"\n" + Path(ca).read_bytes())
        for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"):
            os.environ[key] = str(bundle)


async def execute(root: Path, request: Path, output: Path, *, provider=None, session=None):
    """Execute one current Input, optionally in an existing Case's Agent session.

    Args:
        root: Agent unit directory with its manifest and native entrypoint.
        request: JSON invocation envelope containing current input and identity.
        output: Per-invocation artifact directory.
        provider: Optional shared OpenTelemetry provider.
        session: Case-owned AgentSession reused across Inputs; None creates and
            closes a standalone session for this invocation.
    Returns:
        Zero on successful execution, one on a recorded Agent/runtime failure.

    The worker never constructs conversation history or manages Agent databases.
    A shared session reserves its thread identity so different Cases cannot be
    redirected to one checkpoint thread by invocation configuration.
    """
    envelope = json.loads(request.read_text(encoding="utf-8"))
    run_id = envelope["run_id"]
    if envelope.get("schema") != "abb.invocation.v1" or not isinstance(run_id, str):
        raise ValueError("Invalid invocation envelope")
    supplied = envelope.get('observation_context')
    context = {key: supplied[key] for key in ('case_id', 'input_id')
               if isinstance(supplied, dict) and isinstance(supplied.get(key), str)}
    context.update(invocation_id=run_id, agent_id=envelope['agent_id'])
    from agentbench.observe.invocation import InvocationObservation
    observed = InvocationObservation(output, run_id, envelope.get("session_id", run_id),
                                     envelope["framework"], context=context, provider=provider)
    store = observed.store
    owned_session = session is None
    session = session or AgentSession()
    result = {"schema": "abb.result.v1", "run_id": run_id, **context}
    try:
        configure_trust()
        # Agent imports and later lazy imports live only in this worker process.
        sys.path[:0] = [str(root / "agent"), str(root / "agent" / "src")]
        config = dict(envelope.get("config") or {})
        if "callbacks" in config:
            raise ValueError("Host callbacks cannot cross a JSON process boundary")
        config = observed.config(config)
        session_id = envelope.get('session_id', run_id)
        configurable = dict(config.get("configurable") or {})
        if not owned_session and configurable.get("thread_id", session_id) != session_id:
            raise ValueError("A Case invocation cannot override its Agent session thread_id")
        configurable.setdefault("thread_id", session_id)
        config["configurable"] = configurable
        config.setdefault("metadata", {}).update(abb_run_id=run_id)
        store.record("execution_start", input=envelope["input"])
        adapter = session.load(root, envelope)
        interception = InterceptionConfig.from_agent_dir(root)
        hosts = [host for route in (*interception.routes, *interception.tool_routes)
                 for host in route.host_patterns] if interception else []
        with model_correlation(hosts):
            invocation = await adapter.ainvoke(envelope["input"], run_config=config)
        result.update(status="succeeded", output=invocation.output, raw_output=invocation.raw_output)
        store.record("execution_end", output=invocation.output)
    except BaseException as exc:
        status = ('cancelled' if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)) else
                  'timeout' if isinstance(exc, TimeoutError) else 'failed')
        result.update(status=status, error_type=type(exc).__name__, error=str(exc))
        store.record("execution_error", error_type=type(exc).__name__, error=str(exc))
    finally:
        if owned_session:
            try:
                await session.aclose()
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

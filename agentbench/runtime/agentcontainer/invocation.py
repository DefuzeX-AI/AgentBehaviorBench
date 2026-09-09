"""Host-side one-shot delivery; native service callers remain a separate strategy."""
from __future__ import annotations

import json
import tempfile
import time
import subprocess
from pathlib import Path
from uuid import uuid4

from agentbench.adapter import AdapterInvocation
from agentbench.observe.store import atomic_json


def invoke_once(runtime, agent, value, config=None, *, cancelled=None):
    run_id = uuid4().hex
    base = runtime.artifact_root
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="invocation-", dir=base))
    inputs, outputs = directory / "input", directory / "output"
    inputs.mkdir(mode=0o755)
    outputs.mkdir(mode=0o777)
    outputs.chmod(0o777)  # Only this fresh mount is writable by the image's non-root UID.
    envelope = {"schema": "abb.invocation.v1", "run_id": run_id,
                "session_id": runtime.run_id or run_id,
                "agent_id": agent.agent_id, "framework": agent.framework,
                "input": value, "config": config}
    # Strict JSON boundary: do not stringify host callbacks or arbitrary objects.
    (inputs / "request.json").write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
    session = None
    try:
        session = runtime.start(agent, invocation=(inputs, outputs))
        deadline = time.monotonic() + runtime.invocation_timeout(agent)
        while True:
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Invocation cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Agent execution timed out; diagnostics: {directory}")
            try:
                code = session.wait(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        path = outputs / "result.json"
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"Worker exited {code} without a result: {directory}")
        if path.stat().st_size > 32 * 1024 * 1024:
            raise RuntimeError("Worker result exceeds the 32 MiB limit")
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("schema") != "abb.result.v1" or result.get("run_id") != run_id or result.get("agent_id") != agent.agent_id:
            raise RuntimeError("Worker result does not belong to this invocation")
        if code != 0 or result.get("status") != "succeeded":
            raise RuntimeError(f"Worker failed ({code}): {result.get('error', 'unknown error')}")
        if "output" not in result or "raw_output" not in result:
            raise RuntimeError("Incomplete worker result")
        session.validate_trace(0)
        return AdapterInvocation(output=result["output"], raw_output=result["raw_output"])
    finally:
        if session is not None:
            try:
                session.close()
            finally:
                atomic_json(directory / "diagnostics.json", {
                    "returncode": session.returncode, "stdout": session.stdout, "stderr": session.stderr})

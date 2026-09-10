# AgentBehaviorBench — 10 defects, with reproductions and fixes

Findings from an end-to-end test of the current checkout, written as ten
independent issue reports. Each one is self-contained: it names the defect,
quotes the source it comes from, states the impact, proposes a fix as a diff,
and carries a reproduction script that needs nothing but this repository.

**Every reproduction script exits 0 while the defect still holds.** Nine of the
ten need no credentials, no network and no Docker; the first one needs Docker
only. All ten were verified on 2026-09-10 (10/10).

## What was tested

| | |
| --- | --- |
| Repository | `YaoAnthony/AgentBehaviorBench` @ `e87bf3e` |
| Agent under test | `langchain-ai/react-agent` — the official LangGraph ReAct template |
| Host | Linux 7.0.0-30-generic, Docker Engine 29.8.0 (native, not Desktop), Python 3.12.3 |
| Libraries | langgraph 1.2.11 · langchain-core 1.6.2 · langchain-openai 1.6.2 · openai 3.11.0 · httpx 0.28.1 · httpx2 2.12.0 · langchain-tavily 0.2.18 · node 26.5.0 |
| Model / tools used | DeepSeek `deepseek-chat` over an OpenAI-compatible endpoint, real Tavily search |
| Test suite as shipped | `python -m pytest` → 258 passed, 5 failed, 19 skipped (3 of the failures need the private KUMA SDK; 2 are issue #9 below) |

The Agent was onboarded without modifying a single line of its upstream source,
and the AgentBehaviorBench checkout stayed read-only throughout — `git status`
was clean before and after.

Two execution paths were exercised end to end:

- **host-side** — `runtime.type = "in_process"`, driven by `certify` with a
  substitute evaluation SDK: three inputs, a Judge report, `adapting` → `ready`.
- **container** — `runtime.type = "docker"` with the Model Interceptor, driven by
  `observe`: 10 framework spans, 43 OTel spans, 2 intercepted model calls, 1
  intercepted tool call. This path required the fix in issue #1 before it ran at all.

## The ten

| # | Module | Issue | Repro |
| --- | --- | --- | --- |
| 1 | `docker` | [Model Interceptor cannot create its CA on native Linux Docker: every interception run dies at startup](#1-docker-model-interceptor-cannot-create-its-ca-on-native-linux-docker-every-interception-run-dies-at-startup)<br>Interception cannot start at all on native Linux Docker. One `chmod` fixes it. | Docker |
| 2 | `benchmark_runner` | [Host benchmark path only calls the synchronous invoke(), so async-only LangGraph nodes always fail](#2-benchmark_runner-host-benchmark-path-only-calls-the-synchronous-invoke-so-async-only-langgraph-nodes-always-fail)<br>The host path never calls `ainvoke`, so async-only LangGraph nodes always fail. | offline |
| 3 | `correlation` | [framework_span_id is null on every real model call: the OpenAI SDK uses httpx2, which is not patched](#3-correlation-framework_span_id-is-null-on-every-real-model-call-the-openai-sdk-uses-httpx2-which-is-not-patched)<br>`correlation.py` patches `httpx`; the OpenAI SDK imports `httpx2`. Span links are lost. | offline |
| 4 | `langgraph` | [No channel to supply a LangGraph 1.x Runtime[Context], so runtime.context is None for every such Agent](#4-langgraph-no-channel-to-supply-a-langgraph-1x-runtimecontext-so-runtimecontext-is-none-for-every-such-agent)<br>No way to pass a LangGraph 1.x `Runtime[Context]`, so `runtime.context` is `None`. | offline |
| 5 | `cli` | [`certify` and `run` have no --registry, so an external Agent workspace cannot complete its lifecycle](#5-cli-certify-and-run-have-no---registry-so-an-external-agent-workspace-cannot-complete-its-lifecycle)<br>`certify` and `run` cannot be pointed at an external registry. | offline |
| 6 | `evaluate` | [`evaluate` discards the BenchmarkResult, so a third-party SDK writes nothing and --output silently does nothing](#6-evaluate-evaluate-discards-the-benchmarkresult-so-a-third-party-sdk-writes-nothing-and---output-silently-does-nothing)<br>`evaluate` throws away the result; a third-party SDK writes nothing. | offline |
| 7 | `observe` | [In-process runs emit no artifact_directory, leaving four of the viewer's five tabs empty with no explanation](#7-observe-in-process-runs-emit-no-artifact_directory-leaving-four-of-the-viewers-five-tabs-empty-with-no-explanation)<br>In-process runs leave four of the viewer's five tabs blank, silently. | offline |
| 8 | `viewer` | [`agentbench view` returns 503 on a fresh clone: web/dist is gitignored and the build step is undocumented](#8-viewer-agentbench-view-returns-503-on-a-fresh-clone-webdist-is-gitignored-and-the-build-step-is-undocumented)<br>`agentbench view` answers 503 on a fresh clone; the build step is undocumented. | offline |
| 9 | `registry` | [Bundled registry marks company-research-agent ready, contradicting docs/Agents/Layout.md and its own tests](#9-registry-bundled-registry-marks-company-research-agent-ready-contradicting-docsagentslayoutmd-and-its-own-tests)<br>The shipped registry contradicts the repo's own docs and tests. | offline |
| 10 | `registry` | [A Dockerfile is required from Agents whose runtime.type is in_process and which are never containerised](#10-registry-a-dockerfile-is-required-from-agents-whose-runtimetype-is-in_process-and-which-are-never-containerised)<br>A Dockerfile is demanded from Agents that are never containerised. | offline |

## How to read one

Each section is ordered the same way:

**Summary** → **Environment** → **Root cause** (the actual source, with
`file:line`) → **Impact** → **Suggested fix** (a diff) → **Reproduction script**
(complete, in a collapsed block) → **Verbatim output** (what that script printed
here).

The scripts are deliberately independent of each other and of any private
tooling. Save one to a file, `pip install -e` this repository, and run it.

---

## 1. [docker] Model Interceptor cannot create its CA on native Linux Docker: every interception run dies at startup

### Summary

Every interception-mode run fails on native Linux Docker before the Agent is
reached. The Model Interceptor container cannot create its CA:

```
[08:43:00.473] Addon error: [Errno 13] Permission denied: '/run/defuzex/ca/mitmproxy-ca.pem'
```

`DockerRuntime._start_interceptor` creates the CA export directory with a bare
`mkdir()`, so it is owned by the host user. `InterceptorPolicy` then runs the
interceptor with `--cap-drop=ALL --cap-add=NET_ADMIN --cap-add=NET_RAW`, i.e.
without `CAP_DAC_OVERRIDE`, so container-root cannot create a file in a directory
owned by another uid. mitmproxy aborts during startup.

Docker Desktop on macOS and Windows fakes bind-mount ownership, which is why this
never shows up there. The documentation is all PowerShell, so I suspect the
project is developed on Windows and this path is simply untested on Linux.

### Environment

- AgentBehaviorBench `e87bf3e`
- Docker Engine 29.8.0, native Linux (Linux 7.0.0-30-generic), non-rootless
- Python 3.12.3
- Reproduces with any Agent whose manifest sets `llm_interception.required = true`

### Root cause

`agentbench/runtime/docker/runtime.py:248-252`

```python
        secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
        config_file = secret_dir / "interceptor_config.json"
        ca_dir = secret_dir / "ca"
        ca_dir.mkdir()
        ca_certificate = ca_dir / "mitmproxy-ca-cert.pem"
```

`ca_dir.mkdir()` takes the process umask, so the directory ends up `0755`/`0775`
owned by the host uid.

`agentbench/runtime/docker/runtime.py:322-324` mounts it writable:

```python
                "--mount",
                _writable_bind_mount(ca_dir, "/run/defuzex/ca"),
```

`agentbench/runtime/docker/interceptor_policy.py:15-27` drops the capability that
would let container-root ignore those permission bits:

```python
    def run_arguments(self) -> tuple[str, ...]:
        return (
            "--read-only",
            "--cap-drop=ALL",
            "--cap-add=NET_ADMIN",
            "--cap-add=NET_RAW",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs=/run/defuzex:rw,noexec,nosuid,size=64m",
        )
```

The `--tmpfs=/run/defuzex` line does not help: the bind mount is layered at
`/run/defuzex/ca` and carries the host directory's ownership.

mitmproxy then fails here, on first startup, when it tries to generate the store:

```
  File "/usr/local/lib/python3.12/site-packages/mitmproxy/addons/tlsconfig.py", line 479, in configure
    self.certstore = certs.CertStore.from_store(
  File "/usr/local/lib/python3.12/site-packages/mitmproxy/certs.py", line 528, in from_store
    cls.create_store(path, basename, key_size)
  File "/usr/local/lib/python3.12/site-packages/mitmproxy/certs.py", line 578, in create_store
    (path / f"{basename}-ca.pem").write_bytes(
PermissionError: [Errno 13] Permission denied: '/run/defuzex/ca/mitmproxy-ca.pem'
```

Note when diagnosing this: `touch` on a path that already exists succeeds even
without `CAP_DAC_OVERRIDE`, so a naive write probe reports a false negative. The
probe in the script below creates a new file, as `create_store` does.

### Impact

`observe`, `run` and `certify` all fail for any Agent with
`llm_interception.required = true`, which is the configuration the bundled
`01-company-research-agent` ships with. The failure happens at interceptor
startup, so no Agent code runs and no evidence is produced. Since the Docker
path is also the only one that writes `network.jsonl`, `framework.jsonl` and
`otel.jsonl`, this takes the trace viewer's evidence tabs down with it.

### Suggested fix

Relax only the CA export directory, and leave the `mkdtemp` parent at `0700` so
the exported certificate stays private on the host. Adding `CAP_DAC_OVERRIDE`
would work too but weakens the interceptor policy for one directory's sake.

```diff
--- a/agentbench/runtime/docker/runtime.py
+++ b/agentbench/runtime/docker/runtime.py
@@
+# The interceptor container runs with --cap-drop=ALL and no CAP_DAC_OVERRIDE,
+# so container-root can only write into this bind mount if the mode allows it.
+# The mkdtemp parent stays 0700, so the exported CA is still private per user.
+CA_EXPORT_DIR_MODE = 0o777
+
@@
         secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
         config_file = secret_dir / "interceptor_config.json"
         ca_dir = secret_dir / "ca"
         ca_dir.mkdir()
+        ca_dir.chmod(CA_EXPORT_DIR_MODE)
         ca_certificate = ca_dir / "mitmproxy-ca-cert.pem"
```

Verified: with that single `chmod`, the same `observe` command that failed above
completes and produces a full evidence set.

```
Status: succeeded
Trace: {'framework:execution_start': 1, 'framework:span_start': 10, 'framework:span_end': 10,
        'framework:execution_end': 1, 'otel:span': 43,
        'interceptor:interceptor_ready': 1, 'interceptor:llm_request': 2, 'interceptor:llm_response': 2,
        'interceptor:tool_request': 1, 'interceptor:tool_response': 1}
```

A regression test that does not need mitmproxy: create the directory the way
`_start_interceptor` does and assert the mode permits other-write, or run a
throwaway container under `InterceptorPolicy().run_arguments()` and assert it can
create a new file in the mount.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: the Model Interceptor cannot create its CA on Linux Docker.

Requires Docker. No credentials, no model calls, no paid services: the
interceptor dies during startup, long before any request is routed.

    pip install -e /path/to/AgentBehaviorBench
    python repro_ca_dir_permission.py

DockerRuntime._start_interceptor creates the CA export directory with a bare
ca_dir.mkdir(), so it is owned by the host user. InterceptorPolicy runs the
interceptor with --cap-drop=ALL --cap-add=NET_ADMIN --cap-add=NET_RAW, i.e.
without CAP_DAC_OVERRIDE, so container-root cannot create a file in it and
mitmproxy aborts with

    PermissionError: [Errno 13] Permission denied: '/run/defuzex/ca/mitmproxy-ca.pem'

Docker Desktop on macOS and Windows fakes bind-mount ownership, which is why this
does not surface there. Every interception-mode run fails on native Linux Docker.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import inspect
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

BASE_IMAGE = "python:3.12-slim"
PROBE_FILE = "mitmproxy-ca.pem"


def main() -> int:
    from agentbench.runtime.docker import runtime as runtime_module
    from agentbench.runtime.docker.interceptor_policy import InterceptorPolicy

    print("=" * 72)
    print("A. How the CA export directory is created")
    print("=" * 72)
    source = inspect.getsource(runtime_module.DockerRuntime._start_interceptor)
    for line in source.splitlines():
        if "mkdtemp" in line or "ca_dir" in line or "chmod" in line:
            print(f"  {line.strip()}")
    has_chmod = "ca_dir.chmod" in source
    print(f"  ca_dir.chmod present: {has_chmod}\n")

    print("=" * 72)
    print("B. The capability set the interceptor runs under")
    print("=" * 72)
    policy_args = InterceptorPolicy().run_arguments()
    for argument in policy_args:
        if "cap" in argument or "read-only" in argument:
            print(f"  {argument}")
    has_dac_override = any("DAC_OVERRIDE" in a.upper() for a in policy_args)
    print(f"  CAP_DAC_OVERRIDE granted: {has_dac_override}\n")

    print("=" * 72)
    print("C. Reproducing the directory exactly as the runtime does")
    print("=" * 72)
    secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
    ca_dir = secret_dir / "ca"
    ca_dir.mkdir()
    mode = stat.S_IMODE(ca_dir.stat().st_mode)
    print(f"  path : {ca_dir}")
    print(f"  owner: uid={ca_dir.stat().st_uid} gid={ca_dir.stat().st_gid}")
    print(f"  mode : {mode:04o}  (others may write: {bool(mode & stat.S_IWOTH)})\n")

    if shutil.which("docker") is None:
        print("  docker not on PATH; skipping the container probe")
        shutil.rmtree(secret_dir, ignore_errors=True)
        return 0 if not has_chmod and not has_dac_override else 1

    print("=" * 72)
    print("D. Container-root creating a new file there, under that exact policy")
    print("=" * 72)
    command = [
        "docker", "run", "--rm", *policy_args,
        "--mount", f"type=bind,source={ca_dir.resolve()},target=/run/defuzex/ca",
        BASE_IMAGE,
        # A NEW file, as mitmproxy's certs.create_store does. Touching a file
        # that already exists succeeds even without the capability.
        "python", "-c",
        f"open('/run/defuzex/ca/{PROBE_FILE}', 'wb').write(b'x')",
    ]
    print(f"  $ docker run ... --cap-drop=ALL ... {BASE_IMAGE}")
    print(f"    python -c \"open('/run/defuzex/ca/{PROBE_FILE}', 'wb').write(b'x')\"")
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"  exit code: {proc.returncode}")
    for line in (proc.stdout + proc.stderr).strip().splitlines()[-4:]:
        print(f"  {line}")
    print()

    print("=" * 72)
    print("E. The same probe with the one-line fix applied")
    print("=" * 72)
    ca_dir.chmod(0o777)
    print(f"  ca_dir.chmod(0o777) -> mode {stat.S_IMODE(ca_dir.stat().st_mode):04o}")
    fixed = subprocess.run(command, capture_output=True, text=True, check=False)
    print(f"  exit code: {fixed.returncode}")
    for line in (fixed.stdout + fixed.stderr).strip().splitlines()[-3:]:
        print(f"  {line}")
    print(f"  parent directory stays private: mode "
          f"{stat.S_IMODE(secret_dir.stat().st_mode):04o}\n")

    denied = "Permission denied" in (proc.stdout + proc.stderr)
    shutil.rmtree(secret_dir, ignore_errors=True)

    if not has_chmod and not has_dac_override and proc.returncode != 0 and denied and fixed.returncode == 0:
        print(
            "RESULT: reproduced — the interceptor container cannot create its CA,\n"
            "        so every interception-mode run fails at startup on native\n"
            "        Linux Docker. Relaxing only the CA directory fixes it."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
========================================================================
A. How the CA export directory is created
========================================================================
  secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
  ca_dir = secret_dir / "ca"
  ca_dir.mkdir()
  ca_certificate = ca_dir / "mitmproxy-ca-cert.pem"
  _writable_bind_mount(ca_dir, "/run/defuzex/ca"),
  ca_dir.chmod present: False

========================================================================
B. The capability set the interceptor runs under
========================================================================
  --read-only
  --cap-drop=ALL
  --cap-add=NET_ADMIN
  --cap-add=NET_RAW
  CAP_DAC_OVERRIDE granted: False

========================================================================
C. Reproducing the directory exactly as the runtime does
========================================================================
  path : /tmp/defuzex-model-interceptor-bxplqrbr/ca
  owner: uid=1000 gid=1000
  mode : 0775  (others may write: False)

========================================================================
D. Container-root creating a new file there, under that exact policy
========================================================================
  $ docker run ... --cap-drop=ALL ... python:3.12-slim
    python -c "open('/run/defuzex/ca/mitmproxy-ca.pem', 'wb').write(b'x')"
  exit code: 1
  Traceback (most recent call last):
    File "<string>", line 1, in <module>
  PermissionError: [Errno 13] Permission denied: '/run/defuzex/ca/mitmproxy-ca.pem'

========================================================================
E. The same probe with the one-line fix applied
========================================================================
  ca_dir.chmod(0o777) -> mode 0777
  exit code: 0
  parent directory stays private: mode 0700

RESULT: reproduced — the interceptor container cannot create its CA,
        so every interception-mode run fails at startup on native
        Linux Docker. Relaxing only the CA directory fixes it.
```

</details>

---

## 2. [benchmark_runner] Host benchmark path only calls the synchronous invoke(), so async-only LangGraph nodes always fail

### Summary

The host benchmark path only ever calls the synchronous `invoke()`, so any Agent
whose LangGraph nodes are `async def` fails before it can produce anything:

```
TypeError: No synchronous function provided to "call_model".
Either initialize with a synchronous function or invoke via the async API (ainvoke, astream, etc.)
```

`RunningAgent.ainvoke` already exists and does the right thing, but nothing in
`agentbench/harness/` calls it — it is the only definition and there are no call
sites. The container worker takes the correct path (`await adapter.ainvoke(...)`),
so the same Agent behaves differently depending on `runtime.type`.

Async nodes are the default in the official LangGraph ReAct template
(`langchain-ai/react-agent`, whose `call_model` is `async def`), so this is not
an edge case: the canonical LangGraph starter cannot run in-process.

### Environment

- AgentBehaviorBench `e87bf3e`
- langgraph 1.2.11, langchain-core 1.6.2, Python 3.12.3
- `runtime.type = "in_process"`; no Docker, credentials or model calls involved

### Root cause

`agentbench/harness/runner/benchmark_runner.py:303-315` — the only invocation the
suite makes:

```python
        while (test_input := sdk_run.get_input(full=True)) is not None:
            ...
            try:
                invocation = running.invoke(
                    test_input.payload,
                    run_config=run_config,
                )
```

`agentbench/harness/runner/running_agent.py:38-51` — both handles exist:

```python
    def invoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        if not self.is_running:
            raise AgentNotRunningError(f"Agent is not running: {self.agent_id}")
        return self.adapter.invoke(value, run_config=run_config)

    async def ainvoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        if not self.is_running:
            raise AgentNotRunningError(f"Agent is not running: {self.agent_id}")
        return await self.adapter.ainvoke(value, run_config=run_config)
```

`grep -rn "ainvoke" agentbench/harness/` returns only those two lines: the
definition. There is no caller.

`agentbench/adapter/langgraph/adapter.py:68-77` shows `ainvoke` already handles
graphs that lack an async path, so routing everything through it is safe:

```python
        async_invoke = getattr(graph, "ainvoke", None)
        if callable(async_invoke):
            raw_output = await async_invoke(graph_input, config=run_config)
        else:
            raw_output = await asyncio.to_thread(
                graph.invoke, graph_input, config=run_config
            )
```

By contrast `agentbench/runtime/agentcontainer/worker.py` does the right thing:

```python
            invocation = await adapter.ainvoke(envelope["input"], run_config=config)
```

### Impact

- `run`, `certify` and `evaluate` cannot execute any in-process Agent with async
  nodes, which includes the official `langchain-ai/react-agent` template.
- The failure surfaces as `AgentInvocationError: Agent 'X' failed for SDK Input
  'Y'`. The underlying `TypeError` is chained but `SuiteAgentResult.error_message`
  keeps only the outer sentence, so the actual cause is not in the artifact.
- The only workaround today is a per-Agent `bindings/*.py` that wraps the graph
  in `asyncio.run`, which turns the binding escape hatch into a requirement for
  ordinary Agents.

### Suggested fix

Drive the handshake through the async handle that already exists, and run the
loop under `asyncio.run` the way the container worker does.

```diff
--- a/agentbench/harness/runner/benchmark_runner.py
+++ b/agentbench/harness/runner/benchmark_runner.py
@@
+import asyncio
+
@@
-            try:
-                invocation = running.invoke(
-                    test_input.payload,
-                    run_config=run_config,
-                )
+            try:
+                invocation = asyncio.run(
+                    running.ainvoke(
+                        test_input.payload,
+                        run_config=run_config,
+                    )
+                )
```

`LangGraphAdapter.ainvoke` falls back to `asyncio.to_thread(graph.invoke, ...)`
for graphs with no async path, so sync-only Agents keep working.

While here, it would help to carry the cause into the artifact:

```diff
--- a/agentbench/harness/runner/benchmark_runner.py
+++ b/agentbench/harness/runner/benchmark_runner.py
@@
                 raise AgentInvocationError(
                     f"Agent {registration.agent_id!r} failed for "
-                    f"SDK Input {test_input.input_id!r}"
+                    f"SDK Input {test_input.input_id!r}: "
+                    f"{type(exc).__name__}: {exc}"
                 ) from exc
```

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: the host benchmark path cannot run an async-only LangGraph node.

Self-contained. No credentials, no network, no Docker, no model calls.

    pip install -e /path/to/AgentBehaviorBench
    python repro_sync_invoke.py

Builds a throwaway Agent unit whose graph has a single `async def` node, registers
it, and runs it through SuiteRunner with a trivial offline SDK.

Expected (if the host path used ainvoke): the suite passes.
Actual: TypeError: No synchronous function provided to "echo".

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path
from uuid import uuid4

# --------------------------------------------------------------------------
# 1. A throwaway Agent unit in the layout docs/Agents/Layout.md describes.
# --------------------------------------------------------------------------

GRAPH_PY = '''\
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


async def echo(state: State) -> dict:
    """Async-only node: LangGraph refuses to run it from a synchronous invoke()."""
    return {"text": state["text"].upper()}


builder = StateGraph(State)
builder.add_node("echo", echo)
builder.add_edge(START, "echo")
builder.add_edge("echo", END)
graph = builder.compile()
'''

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "async-echo"
display_name = "Async-only echo"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''

REGISTRY_TOML = '''\
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "async-echo"
path = "resources/agents/async-echo"
enabled = true
status = "ready"
framework = "langgraph"
source = "local"
case = 1
'''


def build_workspace(root: Path) -> Path:
    unit = root / "resources" / "agents" / "async-echo"
    (unit / "agent").mkdir(parents=True)
    (unit / "agent" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "./graph.py:graph"}}), encoding="utf-8"
    )
    (unit / "agent.toml").write_text(AGENT_TOML, encoding="utf-8")
    (unit / "requirement.md").write_text("# Uppercase the input text.\n", encoding="utf-8")
    # registry.py requires a Dockerfile even for runtime.type = "in_process".
    (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    registry = root / "resources" / "registry.toml"
    registry.write_text(REGISTRY_TOML, encoding="utf-8")
    return registry


# --------------------------------------------------------------------------
# 2. The smallest SDK that satisfies the documented create_run() contract.
# --------------------------------------------------------------------------

class Input:
    def __init__(self, input_id: str, payload: object) -> None:
        self.input_id = input_id
        self.payload = payload


class Report:
    def __init__(self, status: str) -> None:
        self.status = status
        self.confidence = 1.0
        self.issues: tuple = ()
        self.evidence_gaps: tuple = ()


class Run:
    def __init__(self) -> None:
        self.run_id = f"repro_{uuid4().hex[:8]}"
        self.state = "ready"
        self.report: Report | None = None
        self.history: tuple = ()
        self._pending = True

    def get_input(self, *, full: bool = False):
        if not self._pending:
            return None
        self.state = "input_delivered"
        return Input("only", "hello")

    def submit(self, output=None, *, status="completed", error=None):
        self._pending = False
        self.history = ({"input_id": "only", "output": output, "status": status},)
        self.report = Report("pass" if output == "HELLO" else "issue")
        self.state = "report_ready"
        return self.report


def create_run(*, repo_path, **_):
    del repo_path
    return Run()


# --------------------------------------------------------------------------
# 3. Drive it three ways: the suite, the synchronous adapter, the async adapter.
# --------------------------------------------------------------------------

def main() -> int:
    import asyncio

    from agentbench.adapter.langgraph.adapter import LangGraphAdapter
    from agentbench.harness import SuiteRunner, load_registry

    root = Path(tempfile.mkdtemp(prefix="abb-async-repro-"))
    registry_path = build_workspace(root)
    agents = load_registry(registry_path).ready()
    unit = root / "resources" / "agents" / "async-echo"
    print(f"workspace : {root}")
    print(f"registered: {[a.agent_id for a in agents]}\n")

    print("=" * 72)
    print("A. SuiteRunner (the documented host-side entry point)")
    print("=" * 72)
    result = SuiteRunner(sdk=sys.modules[__name__]).run(agents)
    item = result.items[0]
    print(f"  passed       : {result.passed}")
    print(f"  error_type   : {item.error_type}")
    print(f"  error_message: {item.error_message}")
    print("  (the underlying TypeError is chained but not reported here)\n")

    print("=" * 72)
    print("B. LangGraphAdapter.invoke() — what the host path actually calls")
    print("=" * 72)
    sync_error = None
    adapter = LangGraphAdapter.from_agent_dir(unit).load()
    try:
        adapter.invoke("hello")
    except Exception as exc:
        sync_error = exc
        traceback.print_exc()
    print()

    print("=" * 72)
    print("C. LangGraphAdapter.ainvoke() — same graph, same input")
    print("=" * 72)
    async_output = asyncio.run(adapter.ainvoke("hello")).output
    print(f"  output: {async_output!r}\n")

    reproduced = (
        item.error_type == "AgentInvocationError"
        and isinstance(sync_error, TypeError)
        and async_output == "HELLO"
    )
    if reproduced:
        print(
            "RESULT: reproduced — ainvoke() returns 'HELLO', invoke() raises TypeError,\n"
            "        and the host benchmark path only ever calls invoke()."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
Traceback (most recent call last):
  File "/home/wy/projects/DefuzeX/test/issues/abb_sync_invoke_async_node/repro_sync_invoke.py", line 178, in main
    adapter.invoke("hello")
  File "/home/wy/projects/DefuzeX/AgentBehaviorBench/agentbench/adapter/langgraph/adapter.py", line 43, in invoke
    raw_output = graph.invoke(graph_input, config=run_config)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/main.py", line 3913, in invoke
    for chunk in self.stream(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/main.py", line 2967, in stream
    for _ in runner.tick(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/_runner.py", line 207, in tick
    run_with_retry(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/_retry.py", line 617, in run_with_retry
    return task.proc.invoke(task.input, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/_internal/_runnable.py", line 707, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/_internal/_runnable.py", line 378, in invoke
    raise TypeError(
TypeError: No synchronous function provided to "echo".
Either initialize with a synchronous function or invoke via the async API (ainvoke, astream, etc.)
During task with name 'echo' and id 'd08b7945-cd9f-e8cd-0074-b34587eb5771'
workspace : /tmp/abb-async-repro-e_cxu2er
registered: ['async-echo']

========================================================================
A. SuiteRunner (the documented host-side entry point)
========================================================================
  passed       : False
  error_type   : AgentInvocationError
  error_message: Agent 'async-echo' failed for SDK Input 'only'
  (the underlying TypeError is chained but not reported here)

========================================================================
B. LangGraphAdapter.invoke() — what the host path actually calls
========================================================================

========================================================================
C. LangGraphAdapter.ainvoke() — same graph, same input
========================================================================
  output: 'HELLO'

RESULT: reproduced — ainvoke() returns 'HELLO', invoke() raises TypeError,
        and the host benchmark path only ever calls invoke().
```

</details>

---

## 3. [correlation] framework_span_id is null on every real model call: the OpenAI SDK uses httpx2, which is not patched

### Summary

`framework_span_id` is `null` on every network record produced by a real Agent,
so the two evidence streams the Observe module collects can never be joined.

`observe/correlation.py` injects `x-abb-framework-span` by patching
`httpx.AsyncClient.send`, `httpx.Client.send` and `requests.Session.send`. The
OpenAI SDK does not use that `httpx`: `openai/_base_client.py` does
`import httpx2`, a separate distribution whose `AsyncClient` is a different class
object. Nothing is patched on the path that every OpenAI-compatible Agent
actually takes, so the header is never attached. `langchain-tavily`'s async path
uses `aiohttp`, which is also unpatched, so tool records lose their span too.

The correlation code itself is correct — a plain `httpx` call in the same async
node does get the header. Only the clients real Agents use are missed.

To the project's credit nothing is fabricated: `link_evidence` and
`framework_span_id` are honestly reported as `null` rather than inferred from
timestamps, which matches `docs/observe/architecture.md`'s own warning that
proximity in time is not a parent/child relationship. The result is still that
the documented capability does not work.

### Environment

- AgentBehaviorBench `e87bf3e`
- openai 3.11.0, httpx2 2.12.0, httpx 0.28.1, langchain-openai 1.6.2,
  langchain-tavily 0.2.18, langgraph 1.2.11, Python 3.12.3
- Observed first on a real Docker `observe` run, then isolated offline with a
  loopback server (script below)

### Evidence from a real run

A Docker `observe` run of `langchain-ai/react-agent` against DeepSeek and Tavily
recorded a complete framework trace and a complete network trace, with no link
between them. `network.jsonl`:

```
[1] llm_request    framework_span_id = None   call_id=call_08629d41b8c24cdca00
[2] llm_response   framework_span_id = None   call_id=call_08629d41b8c24cdca00
[3] tool_request   framework_span_id = None   call_id=call_781d6d56ff1549faafa
[4] tool_response  framework_span_id = None   call_id=call_781d6d56ff1549faafa
[5] llm_request    framework_span_id = None   call_id=call_5c218961defc491ab2f
[6] llm_response   framework_span_id = None   call_id=call_5c218961defc491ab2f
```

`framework.jsonl` from the same invocation has the IDs that should have been
carried:

```
  span_start  span=01a08a7e-7d5b-7752-b  name=ChatOpenAI
  span_start  span=01a08a7e-80f7-78e3-9  name=tavily_search
  span_start  span=01a08a7e-88aa-7a73-a  name=ChatOpenAI
```

### Root cause

`agentbench/observe/correlation.py:16-60`:

```python
@contextmanager
def model_correlation(host_patterns):
    restorations = []

    def add_header(request):
        host = urlsplit(str(request.url)).hostname or ""
        span = current_span.get()
        if span and any(fnmatchcase(host, pattern) for pattern in host_patterns):
            request.headers["x-abb-framework-span"] = span

    try:
        try:
            import httpx
            original_async = httpx.AsyncClient.send
            original_sync = httpx.Client.send
            ...
        except ImportError:
            pass
        try:
            import requests
            original_requests = requests.Session.send
            ...
```

The patched set is `{httpx, requests}`. What real Agents use:

| caller | client | patched |
| --- | --- | --- |
| `langchain-openai` → `openai` SDK | `httpx2` | no |
| `langchain-tavily` async path | `aiohttp` | no |
| `langchain-tavily` sync path | `requests` | yes |
| an Agent calling `httpx` itself | `httpx` | yes |

```
openai/_base_client.py: import httpx2
httpx.AsyncClient      : <class 'httpx.AsyncClient'>
httpx2.AsyncClient     : <class 'httpx2.AsyncClient'>
same class object      : False
```

The interceptor side is fine — `services/model-interceptor/.../addon.py:34,43`
pops the header and records it, and strips it before forwarding upstream:

```python
        span = flow.request.headers.pop("x-abb-framework-span", None)
        flow.metadata.update(..., framework_span_id=span if span and len(span) <= 64 else None)
```

So the value is simply never sent.

### Impact

- `docs/observe/architecture.md` describes network/framework reconciliation as a
  capability of the Observe module. In practice the interaction timeline is
  ordered by timestamp with no causal link, for every Agent that talks to an
  OpenAI-compatible endpoint — which is almost all of them.
- Silent: no warning, no `uncorrelated` marker in the viewer, just `null`.
- It will regress again the next time a client library switches its HTTP stack,
  because the patch list is a hardcoded pair of imports.

### Suggested fix

Patch `httpx2` alongside `httpx`, and add `aiohttp` for tool traffic. Both use
the same `add_header(request)` shape as the existing `httpx` branch.

```diff
--- a/agentbench/observe/correlation.py
+++ b/agentbench/observe/correlation.py
@@
     try:
-        try:
-            import httpx
-            original_async = httpx.AsyncClient.send
-            original_sync = httpx.Client.send
-
-            async def async_send(self, request, *args, **kwargs):
-                add_header(request)
-                return await original_async(self, request, *args, **kwargs)
-
-            def sync_send(self, request, *args, **kwargs):
-                add_header(request)
-                return original_sync(self, request, *args, **kwargs)
-
-            restorations.extend([(httpx.AsyncClient, "send", original_async), (httpx.Client, "send", original_sync)])
-            httpx.AsyncClient.send, httpx.Client.send = async_send, sync_send
-        except ImportError:
-            pass
+        # The OpenAI SDK imports httpx2, whose classes are distinct objects from
+        # httpx's. Patching only one of them silently misses every model call.
+        for module_name in ("httpx", "httpx2"):
+            try:
+                module = importlib.import_module(module_name)
+            except ImportError:
+                continue
+            original_async = module.AsyncClient.send
+            original_sync = module.Client.send
+
+            def make_async(original):
+                async def async_send(self, request, *args, **kwargs):
+                    add_header(request)
+                    return await original(self, request, *args, **kwargs)
+                return async_send
+
+            def make_sync(original):
+                def sync_send(self, request, *args, **kwargs):
+                    add_header(request)
+                    return original(self, request, *args, **kwargs)
+                return sync_send
+
+            restorations.extend([
+                (module.AsyncClient, "send", original_async),
+                (module.Client, "send", original_sync),
+            ])
+            module.AsyncClient.send = make_async(original_async)
+            module.Client.send = make_sync(original_sync)
```

`aiohttp` needs a slightly different hook because it builds the request inside
`ClientSession._request`; adding the header through the `headers` argument works:

```diff
+        try:
+            import aiohttp
+            original_request = aiohttp.ClientSession._request
+
+            async def patched_request(self, method, url, *args, headers=None, **kwargs):
+                span = current_span.get()
+                host = urlsplit(str(url)).hostname or ""
+                if span and any(fnmatchcase(host, p) for p in host_patterns):
+                    headers = dict(headers or {})
+                    headers["x-abb-framework-span"] = span
+                return await original_request(self, method, url, *args, headers=headers, **kwargs)
+
+            restorations.append((aiohttp.ClientSession, "_request", original_request))
+            aiohttp.ClientSession._request = patched_request
+        except ImportError:
+            pass
```

Two things would keep this from silently regressing:

1. A test that drives a real `ChatOpenAI` against a loopback server and asserts
   the header arrives — the script below is one, and it fails today.
2. Surfacing the gap at runtime: when `observe` finishes with model records whose
   `framework_span_id` is `None`, say so in the run summary rather than writing
   `null` and moving on.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: model calls carry no framework span, so network and
framework evidence can never be joined.

Self-contained. No credentials, no external network, no Docker, no paid calls.
A loopback HTTP server stands in for the Model Interceptor and records the
headers it receives.

    pip install -e /path/to/AgentBehaviorBench
    pip install langchain-openai
    python repro_span_correlation.py

docs/observe/architecture.md says model requests carry a framework span ID in a
temporary header so the two evidence streams can be reconciled.
observe/correlation.py injects `x-abb-framework-span` by patching
`httpx.AsyncClient.send`, `httpx.Client.send` and `requests.Session.send`.
The OpenAI SDK imports `httpx2`, a different distribution whose classes are
different objects, so nothing is patched on the path every OpenAI-compatible
Agent actually uses. langchain-tavily's async path uses aiohttp, also unpatched.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

RECEIVED: list[dict] = []

CHAT_COMPLETION = {
    "id": "chatcmpl-repro",
    "object": "chat.completion",
    "created": 0,
    "model": "demo",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "answered"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}

HTTPX_GRAPH = '''\
from typing import TypedDict

import httpx
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


async def call_model(state: State) -> dict:
    """Async node using httpx directly — the client correlation.py patches."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "http://127.0.0.1:{port}/v1/chat/completions",
            json={{"model": "demo", "messages": [{{"role": "user", "content": state["text"]}}]}},
        )
    return {{"text": response.json()["choices"][0]["message"]["content"]}}


builder = StateGraph(State)
builder.add_node("call_model", call_model)
builder.add_edge(START, "call_model")
builder.add_edge("call_model", END)
graph = builder.compile()
'''

OPENAI_GRAPH = '''\
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


async def call_model(state: State) -> dict:
    """Async node using ChatOpenAI — what react-agent and most Agents do."""
    model = ChatOpenAI(model="demo", base_url="http://127.0.0.1:{port}/v1", api_key="unused")
    response = await model.ainvoke(state["text"])
    return {{"text": response.content}}


builder = StateGraph(State)
builder.add_node("call_model", call_model)
builder.add_edge(START, "call_model")
builder.add_edge("call_model", END)
graph = builder.compile()
'''

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "{name}"
display_name = "{name}"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("content-length", 0)))
        RECEIVED.append({key.lower(): value for key, value in self.headers.items()})
        body = json.dumps(CHAT_COMPLETION).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def build_unit(root: Path, port: int, template: str, name: str) -> Path:
    unit = root / "resources" / "agents" / name
    (unit / "agent").mkdir(parents=True)
    module = f"{name.replace('-', '_')}_graph"
    (unit / "agent" / f"{module}.py").write_text(template.format(port=port), encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": f"./{module}.py:graph"}}), encoding="utf-8")
    (unit / "agent.toml").write_text(AGENT_TOML.format(name=name), encoding="utf-8")
    (unit / "requirement.md").write_text("# Call the model once.\n", encoding="utf-8")
    (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return unit


def run_variant(root: Path, port: int, template: str, name: str):
    """Run one Agent wired exactly as runtime/agentcontainer/worker.py wires it."""
    from agentbench.adapter.langgraph.adapter import LangGraphAdapter
    from agentbench.observe.correlation import model_correlation
    from agentbench.observe.observers import DEFAULT_OBSERVERS
    from agentbench.observe.store import TraceStore

    unit = build_unit(root, port, template, name)
    store_path = root / f"framework-{name}.jsonl"
    store = TraceStore(store_path, "reprorun", source="framework")
    adapter = LangGraphAdapter.from_agent_dir(unit).load()
    config: dict = {"configurable": {"thread_id": "reprorun"}}
    callbacks = DEFAULT_OBSERVERS.callbacks("langgraph", store)
    if callbacks:
        config["callbacks"] = callbacks
    before = len(RECEIVED)
    with model_correlation(["127.0.0.1"]):
        output = asyncio.run(adapter.ainvoke("hello", run_config=config)).output
    if hasattr(store, "close"):
        store.close()
    header = RECEIVED[-1].get("x-abb-framework-span") if len(RECEIVED) > before else None
    agent = RECEIVED[-1].get("user-agent", "") if len(RECEIVED) > before else ""
    spans = [
        (json.loads(line)["data"].get("span_id"), json.loads(line)["data"].get("name"))
        for line in store_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("event") == "span_start"
    ]
    return output, header, agent, spans


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    root = Path(tempfile.mkdtemp(prefix="abb-correlation-repro-"))
    print(f"workspace     : {root}")
    print(f"stand-in host : 127.0.0.1:{port}\n")

    print("=" * 72)
    print("A. Control — async node calling httpx, the client correlation.py patches")
    print("=" * 72)
    _, httpx_header, httpx_agent, httpx_spans = run_variant(root, port, HTTPX_GRAPH, "httpx-caller")
    for span_id, name in httpx_spans:
        print(f"  span_start  {span_id}  {name}")
    print(f"  user-agent           : {httpx_agent}")
    print(f"  x-abb-framework-span : {httpx_header!r}\n")

    print("=" * 72)
    print("B. The same Agent using ChatOpenAI, as real Agents do")
    print("=" * 72)
    _, openai_header, openai_agent, openai_spans = run_variant(root, port, OPENAI_GRAPH, "openai-caller")
    for span_id, name in openai_spans:
        print(f"  span_start  {span_id}  {name}")
    print(f"  user-agent           : {openai_agent}")
    print(f"  x-abb-framework-span : {openai_header!r}\n")

    print("=" * 72)
    print("C. Why: the OpenAI SDK does not use the httpx that gets patched")
    print("=" * 72)
    import httpx
    import httpx2
    import openai._base_client as base_client

    for line in inspect.getsource(base_client).splitlines():
        if re.match(r"\s*import\s+httpx", line):
            print(f"  openai/_base_client.py: {line.strip()}")
    print(f"  httpx.AsyncClient      : {httpx.AsyncClient}")
    print(f"  httpx2.AsyncClient     : {httpx2.AsyncClient}")
    print(f"  same class object      : {httpx.AsyncClient is httpx2.AsyncClient}")

    from agentbench.observe import correlation

    patched = sorted(set(re.findall(r"import (httpx2?|requests)",
                                    inspect.getsource(correlation.model_correlation))))
    print(f"  correlation.py patches : {patched}")
    print("  langchain-tavily async path imports aiohttp, also unpatched\n")

    server.shutdown()

    if httpx_header and openai_spans and openai_header is None:
        print(
            "RESULT: reproduced — the header arrives for a plain httpx call and is\n"
            "        absent for the OpenAI SDK, so framework_span_id is None on\n"
            "        every real model record and the two evidence streams cannot\n"
            "        be joined."
        )
        return 0
    print(f"RESULT: not reproduced (httpx={httpx_header!r}, openai={openai_header!r})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
workspace     : /tmp/abb-correlation-repro-5jg7a895
stand-in host : 127.0.0.1:41305

========================================================================
A. Control — async node calling httpx, the client correlation.py patches
========================================================================
  span_start  01a08a92-6537-7660-a344-9d0a748bdbb2  LangGraph
  span_start  01a08a92-6538-7e51-898d-0073cdadd8ff  call_model
  user-agent           : python-httpx/0.28.1
  x-abb-framework-span : '01a08a92-6538-7e51-898d-0073cdadd8ff'

========================================================================
B. The same Agent using ChatOpenAI, as real Agents do
========================================================================
  span_start  01a08a92-678e-7a62-aafc-bc0f8c8e2659  LangGraph
  span_start  01a08a92-678e-7a62-aafc-bc107575970f  call_model
  span_start  01a08a92-684a-7311-899e-5c3614c639b7  ChatOpenAI
  user-agent           : AsyncOpenAI/Python 3.11.0
  x-abb-framework-span : None

========================================================================
C. Why: the OpenAI SDK does not use the httpx that gets patched
========================================================================
  openai/_base_client.py: import httpx2
  httpx.AsyncClient      : <class 'httpx.AsyncClient'>
  httpx2.AsyncClient     : <class 'httpx2.AsyncClient'>
  same class object      : False
  correlation.py patches : ['httpx', 'requests']
  langchain-tavily async path imports aiohttp, also unpatched

RESULT: reproduced — the header arrives for a plain httpx call and is
        absent for the OpenAI SDK, so framework_span_id is None on
        every real model record and the two evidence streams cannot
        be joined.
```

</details>

---

## 4. [langgraph] No channel to supply a LangGraph 1.x Runtime[Context], so runtime.context is None for every such Agent

### Summary

There is no way to give a LangGraph 1.x Agent its runtime context. The adapter
passes `config=` only, and `agent.toml [adapter]` has no field for a context, so
`runtime.context` is `None` for every such Agent and the first line that reads it
raises:

```
AttributeError: 'NoneType' object has no attribute 'model'
```

LangGraph 1.x moved per-run settings out of `config["configurable"]` into
`Runtime[Context]`, supplied as `graph.invoke(input, config=..., context=...)`.
The official `langchain-ai/react-agent` template is written that way — its
`call_model` starts with `load_chat_model(runtime.context.model)` — so it cannot
be onboarded without a custom binding.

### Environment

- AgentBehaviorBench `e87bf3e`
- langgraph 1.2.11, Python 3.12.3
- `runtime.type = "in_process"`; no Docker, credentials or model calls involved

### Root cause

`agentbench/adapter/langgraph/adapter.py:38-77` — both entry points forward
`config` and nothing else:

```python
    def invoke(
        self, value: object, *, run_config: object | None = None
    ) -> AdapterInvocation:
        """Run the graph once."""
        graph = self._require_graph()
        graph_input = self._prepare_input(value)
        raw_output = graph.invoke(graph_input, config=run_config)
```

`agentbench/adapter/langgraph/config.py:24-32` — the manifest schema has no
context field:

```python
@dataclass(frozen=True)
class LangGraphAdapterConfig:
    agent_root: Path
    graph_id: str
    entrypoint: str
    input_key: str | None
    output_key: str | None
    mode: str
    binding: str | None = None
```

`from_agent_dir` reads only `type`, `mode`, `config`, `graph_id`, `input_key`,
`output_key` and `binding` out of `[adapter]`, so there is nothing an Agent
author can declare.

For reference, this is what the official template's node does:

```python
async def call_model(state: State, runtime: Runtime[Context]) -> Dict[str, List[AIMessage]]:
    model = load_chat_model(runtime.context.model).bind_tools(TOOLS)
```

### Impact

- Any Agent using the LangGraph 1.x `Runtime[Context]` API fails on its first
  node, including the official ReAct template.
- The documented escape hatch is `bindings/<name>.py`, but a binding is meant for
  Agents that need special input construction or lifecycle handling
  (`docs/observe/architecture.md`). Needing one just to pass a model name makes
  it mandatory for ordinary LangGraph 1.x Agents.
- The failure is opaque: `AttributeError: 'NoneType' object has no attribute
  'model'` from inside the Agent's own source gives no hint that ABB dropped the
  context.

### Suggested fix

Add a `context` table to `[adapter]` and forward it. Keeping it a plain mapping
avoids importing the Agent's `Context` class in the host.

```diff
--- a/agentbench/adapter/langgraph/config.py
+++ b/agentbench/adapter/langgraph/config.py
@@
 @dataclass(frozen=True)
 class LangGraphAdapterConfig:
     agent_root: Path
     graph_id: str
     entrypoint: str
     input_key: str | None
     output_key: str | None
     mode: str
     binding: str | None = None
+    context: Mapping[str, object] = field(default_factory=dict)
@@
         return cls(
             agent_root=root,
             graph_id=graph_id,
             entrypoint=entrypoint,
             input_key=_optional_string(adapter, "input_key"),
             output_key=_optional_string(adapter, "output_key"),
             mode=mode,
             binding=_optional_string(adapter, "binding"),
+            context=MappingProxyType(dict(adapter.get("context", {}))),
         )
```

```diff
--- a/agentbench/adapter/langgraph/adapter.py
+++ b/agentbench/adapter/langgraph/adapter.py
@@
     def invoke(
         self, value: object, *, run_config: object | None = None
     ) -> AdapterInvocation:
         """Run the graph once."""
         graph = self._require_graph()
         graph_input = self._prepare_input(value)
-        raw_output = graph.invoke(graph_input, config=run_config)
+        raw_output = graph.invoke(graph_input, config=run_config, **self._context_kwargs())
@@
     async def ainvoke(
         self, value: object, *, run_config: object | None = None
     ) -> AdapterInvocation:
         """Run the graph once with async support."""
         graph = self._require_graph()
         graph_input = self._prepare_input(value)
         async_invoke = getattr(graph, "ainvoke", None)
         if callable(async_invoke):
-            raw_output = await async_invoke(graph_input, config=run_config)
+            raw_output = await async_invoke(graph_input, config=run_config, **self._context_kwargs())
+
+    def _context_kwargs(self) -> dict[str, object]:
+        """Pass context= only when declared, so LangGraph 0.x graphs still load."""
+        return {"context": dict(self.config.context)} if self.config.context else {}
```

An Agent then declares its context in the manifest, next to the keys it already
declares:

```toml
[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "messages"
output_key = "messages"

[adapter.context]
model = "openai/gpt-4o-mini"
max_search_results = 3
```

If a graph declares a `context_schema` and no context is supplied, it would also
be worth failing with a message that names the manifest key, instead of letting
the Agent's own source raise `AttributeError` on `None`.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: no channel to supply a LangGraph 1.x runtime context.

Self-contained. No credentials, no network, no Docker, no model calls.

    pip install -e /path/to/AgentBehaviorBench
    python repro_langgraph_context.py

LangGraph 1.x agents read per-run settings from `Runtime[Context]`, which the
caller supplies as `graph.invoke(input, config=..., context=...)`. The ABB
LangGraph adapter passes `config=` only, and `agent.toml [adapter]` has no field
for a context, so `runtime.context` is None for every such Agent.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import traceback
from pathlib import Path

GRAPH_PY = '''\
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime


@dataclass
class Context:
    """Per-run settings, exactly as the official react-agent template declares them."""

    model: str = "unset"


class State(TypedDict):
    text: str


def report_model(state: State, runtime: Runtime[Context]) -> dict:
    # This is the line every LangGraph 1.x agent has; react-agent's is
    #   model = load_chat_model(runtime.context.model)
    return {"text": f"model={runtime.context.model}"}


builder = StateGraph(State, context_schema=Context)
builder.add_node("report_model", report_model)
builder.add_edge(START, "report_model")
builder.add_edge("report_model", END)
graph = builder.compile()
'''

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "context-reader"
display_name = "LangGraph 1.x context reader"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''


def build_unit(root: Path) -> Path:
    unit = root / "resources" / "agents" / "context-reader"
    (unit / "agent").mkdir(parents=True)
    (unit / "agent" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "./graph.py:graph"}}), encoding="utf-8"
    )
    (unit / "agent.toml").write_text(AGENT_TOML, encoding="utf-8")
    (unit / "requirement.md").write_text("# Report the configured model.\n", encoding="utf-8")
    (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return unit


def main() -> int:
    from agentbench.adapter.langgraph.adapter import LangGraphAdapter

    root = Path(tempfile.mkdtemp(prefix="abb-context-repro-"))
    unit = build_unit(root)
    print(f"workspace: {root}\n")

    print("=" * 72)
    print("A. Through the ABB adapter (config= only, no context= channel)")
    print("=" * 72)
    adapter = LangGraphAdapter.from_agent_dir(unit).load()
    adapter_error = None
    try:
        result = asyncio.run(adapter.ainvoke("ignored"))
        print(f"  output: {result.output!r}")
    except Exception as exc:
        adapter_error = exc
        traceback.print_exc()
    print()

    print("=" * 72)
    print("B. Same graph called directly with context=, as LangGraph 1.x intends")
    print("=" * 72)
    import sys

    sys.path.insert(0, str(unit / "agent"))
    from graph import Context, graph  # type: ignore[import-not-found]

    direct = graph.invoke({"text": "ignored"}, context=Context(model="deepseek-chat"))
    print(f"  output: {direct['text']!r}\n")

    print("=" * 72)
    print("C. What agent.toml [adapter] accepts")
    print("=" * 72)
    from dataclasses import fields

    from agentbench.adapter.langgraph.config import LangGraphAdapterConfig

    print(f"  {[f.name for f in fields(LangGraphAdapterConfig)]}")
    print("  no 'context' field, and adapter.invoke/ainvoke pass config= only\n")

    if isinstance(adapter_error, AttributeError) and direct["text"] == "model=deepseek-chat":
        print(
            "RESULT: reproduced — the graph works when given a context and raises\n"
            "        AttributeError through ABB, which has no way to supply one."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
Traceback (most recent call last):
  File "/home/wy/projects/DefuzeX/test/issues/abb_langgraph_context/repro_langgraph_context.py", line 101, in main
    result = asyncio.run(adapter.ainvoke("ignored"))
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/runners.py", line 194, in run
    return runner.run(main)
           ^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/AgentBehaviorBench/agentbench/adapter/langgraph/adapter.py", line 57, in ainvoke
    raw_output = await async_invoke(graph_input, config=run_config)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/main.py", line 4090, in ainvoke
    async for chunk in self.astream(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/main.py", line 3440, in astream
    async for _ in runner.atick(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/_runner.py", line 396, in atick
    await arun_with_retry(
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/pregel/_retry.py", line 744, in arun_with_retry
    return await task.proc.ainvoke(task.input, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/_internal/_runnable.py", line 756, in ainvoke
    input = await asyncio.create_task(
            ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langgraph/_internal/_runnable.py", line 522, in ainvoke
    ret = await self.afunc(*args, **kwargs)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langchain_core/runnables/config.py", line 707, in run_in_executor
    return await asyncio.get_running_loop().run_in_executor(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/concurrent/futures/thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/wy/projects/DefuzeX/test/findings/abb-newrepo-smoke/.venv/lib/python3.12/site-packages/langchain_core/runnables/config.py", line 698, in wrapper
    return func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^
  File "/tmp/abb-context-repro-crgty3g8/resources/agents/context-reader/agent/graph.py", line 22, in report_model
    return {"text": f"model={runtime.context.model}"}
                             ^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'model'
During task with name 'report_model' and id '88a98f91-f85a-1aad-bc9f-76e820784f3e'
workspace: /tmp/abb-context-repro-crgty3g8

========================================================================
A. Through the ABB adapter (config= only, no context= channel)
========================================================================

========================================================================
B. Same graph called directly with context=, as LangGraph 1.x intends
========================================================================
  output: 'model=deepseek-chat'

========================================================================
C. What agent.toml [adapter] accepts
========================================================================
  ['agent_root', 'graph_id', 'entrypoint', 'input_key', 'output_key', 'mode', 'binding']
  no 'context' field, and adapter.invoke/ainvoke pass config= only

RESULT: reproduced — the graph works when given a context and raises
        AttributeError through ABB, which has no way to supply one.
```

</details>

---

## 5. [cli] `certify` and `run` have no --registry, so an external Agent workspace cannot complete its lifecycle

### Summary

`observe` and `evaluate` accept `--registry`. `run` and `certify` do not, even
though `run()` and `certify()` both take a `registry_path` parameter. The flag is
simply not declared on their parsers, so an Agent registered outside the ABB
checkout can be observed and evaluated but never promoted from `adapting` to
`ready` from the CLI.

```
$ python -m agentbench certify some-agent --registry /elsewhere/resources/registry.toml
usage: agentbench [-h] {run,view,certify,observe,evaluate,clean,sdk} ...
agentbench: error: unrecognized arguments: --registry /elsewhere/resources/registry.toml
```

This matters more than it looks, because `load_registry` derives the repository
root from the registry file itself:

```python
    repo_root = registry_file.parent.parent
```

so a registry is fully relocatable — `docs/Agents/Layout.md` documents the
`<root>/resources/registry.toml` shape, and an external workspace keeping that
shape works. Two of the four commands just cannot be pointed at one.

### Environment

- AgentBehaviorBench `e87bf3e`
- Python 3.12.3; no credentials, no Docker, no model calls

### Root cause

`agentbench/cli/features/evaluate.py:17` declares it:

```python
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY_PATH)
```

`agentbench/cli/features/run.py:37-71` and
`agentbench/cli/features/certify.py:30-60` declare `--env-file`, `--output`,
`--model`, `--llm-trace`, `--llm-trace-max-bytes` and the SDK options, but no
`--registry`, and their `execute()` never passes one:

```python
def execute(args: Namespace) -> int:
    load_project_environment(args.env_file)
    try:
        kwargs: dict[str, object] = {"output_path": args.output, **sdk_arguments(args)}
    ...
    return certify(args.agent_id, **kwargs)
```

The functions themselves are ready for it:

```python
def certify(
    agent_id: str,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
```

### Impact

An external Agent workspace can complete only half the documented lifecycle from
the CLI:

| command | external registry |
| --- | --- |
| `observe` | works |
| `evaluate` | works |
| `certify` | not reachable |
| `run` | not reachable |

The remaining options are to edit the repository's own
`resources/registry.toml` — which defeats keeping Agents out of the checkout —
or to drop into the Python API. I used the Python API:

```python
from agentbench.cli.features.certify import certify

certify("react-agent", registry_path="<external>/resources/registry.toml",
        output_path="...", sdk=my_sdk)
```

That worked and promoted the Agent correctly, which confirms the plumbing behind
the flag is fine; only the CLI surface is missing.

### Suggested fix

Declare the flag on both parsers and forward it, exactly as `evaluate` does.

```diff
--- a/agentbench/cli/features/certify.py
+++ b/agentbench/cli/features/certify.py
@@
 def configure_parser(parser: ArgumentParser) -> None:
     configure_sdk_parser(parser)
     parser.add_argument("agent_id", help="Registered adapting Agent to certify.")
+    parser.add_argument(
+        "--registry",
+        type=Path,
+        default=DEFAULT_REGISTRY_PATH,
+        metavar="PATH",
+        help="Agent registry to read (default: the bundled resources/registry.toml).",
+    )
     parser.add_argument(
         "--env-file",
@@
 def execute(args: Namespace) -> int:
     load_project_environment(args.env_file)
     try:
-        kwargs: dict[str, object] = {"output_path": args.output, **sdk_arguments(args)}
+        kwargs: dict[str, object] = {"output_path": args.output,
+                                     "registry_path": args.registry,
+                                     **sdk_arguments(args)}
```

```diff
--- a/agentbench/cli/features/run.py
+++ b/agentbench/cli/features/run.py
@@
 def configure_parser(parser: ArgumentParser) -> None:
     configure_sdk_parser(parser)
+    parser.add_argument(
+        "--registry",
+        type=Path,
+        default=DEFAULT_REGISTRY_PATH,
+        metavar="PATH",
+        help="Agent registry to read (default: the bundled resources/registry.toml).",
+    )
     parser.add_argument(
         "--env-file",
@@
 def execute(args: Namespace) -> int:
     load_project_environment(args.env_file)
     try:
-        kwargs: dict[str, object] = {"output_path": args.output, **sdk_arguments(args)}
+        kwargs: dict[str, object] = {"output_path": args.output,
+                                     "registry_path": args.registry,
+                                     **sdk_arguments(args)}
```

`certify` writes its snapshot to `_default_output_path(registry_path, agent_id)`,
which resolves `repo_root = Path(registry_path).resolve().parent.parent`, so an
external registry also puts the artifacts beside that workspace rather than
inside the ABB checkout. That is the behaviour one would want.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: `certify` and `run` cannot target an external registry.

Self-contained. No credentials, no network, no Docker.

    pip install -e /path/to/AgentBehaviorBench
    python repro_missing_registry_flag.py

`observe` and `evaluate` accept --registry. `certify` and `run` do not, although
their Python entry points both take a registry_path parameter. An Agent
registered outside the ABB checkout can therefore be observed and evaluated but
never promoted from adapting to ready without editing the bundled registry.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import inspect
import subprocess
import sys


def cli_accepts_registry(command: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "agentbench", command, "--help"],
        capture_output=True, text=True, check=False,
    )
    text = proc.stdout + proc.stderr
    return ("--registry" in text), text


def main() -> int:
    print("=" * 72)
    print("A. Which subcommands expose --registry")
    print("=" * 72)
    accepts = {}
    for command in ("run", "certify", "observe", "evaluate"):
        ok, _ = cli_accepts_registry(command)
        accepts[command] = ok
        print(f"  {command:<9} --registry: {'yes' if ok else 'NO'}")
    print()

    print("=" * 72)
    print("B. Their Python entry points do take registry_path")
    print("=" * 72)
    from agentbench.cli.features.certify import certify
    from agentbench.cli.features.run import run

    for name, fn in (("certify", certify), ("run", run)):
        params = list(inspect.signature(fn).parameters)
        print(f"  {name}(): registry_path in signature = {'registry_path' in params}")
    print()

    print("=" * 72)
    print("C. What the CLI does when asked anyway")
    print("=" * 72)
    proc = subprocess.run(
        [sys.executable, "-m", "agentbench", "certify", "some-agent",
         "--registry", "/tmp/elsewhere/resources/registry.toml"],
        capture_output=True, text=True, check=False,
    )
    print(f"  exit code: {proc.returncode}")
    for line in (proc.stdout + proc.stderr).strip().splitlines():
        print(f"  {line}")
    print()

    reproduced = (
        accepts["observe"] and accepts["evaluate"]
        and not accepts["run"] and not accepts["certify"]
        and "unrecognized arguments: --registry" in (proc.stdout + proc.stderr)
    )
    if reproduced:
        print(
            "RESULT: reproduced — certify and run are hardcoded to the bundled\n"
            "        registry even though their functions accept registry_path."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
========================================================================
A. Which subcommands expose --registry
========================================================================
  run       --registry: NO
  certify   --registry: NO
  observe   --registry: yes
  evaluate  --registry: yes

========================================================================
B. Their Python entry points do take registry_path
========================================================================
  certify(): registry_path in signature = True
  run(): registry_path in signature = True

========================================================================
C. What the CLI does when asked anyway
========================================================================
  exit code: 2
  usage: agentbench [-h] {run,view,certify,observe,evaluate,clean,sdk} ...
  agentbench: error: unrecognized arguments: --registry /tmp/elsewhere/resources/registry.toml

RESULT: reproduced — certify and run are hardcoded to the bundled
        registry even though their functions accept registry_path.
```

</details>

---

## 6. [evaluate] `evaluate` discards the BenchmarkResult, so a third-party SDK writes nothing and --output silently does nothing

### Summary

`evaluate` prints one line and throws the `BenchmarkResult` away. Its `--output`
flag is only forwarded into the selected SDK's options, so an evaluation SDK that
does not implement an `output` option leaves nothing on disk — the run completes,
a Judge report is produced, and zero bytes are written.

`docs/CLI.md` says:

> Raw artifacts are saved even without the suite `--output` option.

That holds only for the built-in `kuma` plugin, whose own adapter persists its
files. For any third-party evaluator it is not true, and `--output` fails
silently rather than reporting that the SDK ignored it.

### Environment

- AgentBehaviorBench `e87bf3e`
- Python 3.12.3; no credentials, no Docker, no model calls
- Any SDK implementing only the documented `create_run()` contract

### Root cause

`agentbench/cli/features/evaluate.py:28-58`:

```python
        selected = sdk_arguments(args)
        options = dict(selected.get('sdk_options', {}))
        # Only explicit aliases are forwarded. Each SDK owns its defaults.
        for name in ('sdk_source', 'output', 'timeout'):
            value = getattr(args, name)
            if value is not None:
                options[name] = value
        ...
        result = runner.run(agent)
        if result.report is None:
            raise RuntimeError('The selected SDK completed without a Judge report')
        print(f'Judge: {result.report.status}')
        return 0
```

`result` carries `steps`, each `payload`, each `output`, `raw_output`,
`history_count`, `run_state`, `provider_mode` and the full report. All of it is
dropped after reading `.status`.

The comment "Each SDK owns its defaults" is a reasonable stance for SDK-specific
files, but `BenchmarkResult` is the host's own object, produced by the host
runner, and the host is the only component that can persist it.

Compare `certify` and `run`, which do write a host-side snapshot —
`agentbench/cli/features/certify.py`:

```python
    artifact_base = output_path or _default_output_path(registry_path, agent_id)
```

so `evaluate` is the odd one out.

### Impact

- A third-party evaluator gets one word of terminal output and no evidence. There
  is nothing to inspect, diff, re-judge or attach to a report.
- `--output PATH` accepts a path, exits 0, and creates nothing. Nothing warns the
  user that the selected SDK ignored the option.
- The result is also the input to `agentbench view`, so a third-party evaluation
  cannot be opened in the viewer at all, while `certify` of the same Agent with
  the same SDK can.

### Suggested fix

Write the host-side snapshot in `evaluate` the way `certify` already does, and
keep the option-forwarding behaviour for SDK-specific paths.

```diff
--- a/agentbench/cli/features/evaluate.py
+++ b/agentbench/cli/features/evaluate.py
@@
+from agentbench.cli.result_export import start_result_log
+from agentbench.harness.result import BenchmarkSuiteResult, SuiteAgentResult
@@
         runner.validate_sdk(agent)
         result = runner.run(agent)
         if result.report is None:
             raise RuntimeError('The selected SDK completed without a Judge report')
-        print(f'Judge: {result.report.status}')
+        item = SuiteAgentResult(agent_id=agent.agent_id, benchmarks=(result,),
+                                requested_case_count=1)
+        writer = start_result_log(
+            args.output or _default_output_path(args.registry, agent.agent_id),
+            suite_id=f'evaluate_{uuid4().hex}',
+            selected_agent_ids=(agent.agent_id,),
+        )
+        writer.append_agent_complete(item)
+        writer.append_suite_complete(BenchmarkSuiteResult(
+            suite_id=writer.suite_id, selected_agent_ids=(agent.agent_id,), items=(item,)))
+        print(f'Judge: {result.report.status}')
+        print(f'Result saved: {writer.path}')
+        print(f'Open later: python -m agentbench view {writer.path}')
         return 0
```

`start_result_log`, `append_agent_complete` and `append_suite_complete` already
exist in `agentbench/cli/result_export.py` and are what `certify` and `run` use;
`_default_output_path` is the same helper `certify` has at
`agentbench/cli/features/certify.py:184`. Adapt the constructor keywords to the
current `SuiteAgentResult` / `BenchmarkSuiteResult` fields.

If `--output` should keep doubling as an SDK option alias instead, then say so
when the selected SDK does not consume it, rather than exiting 0 with nothing
written:

```diff
+        if args.output is not None and 'output' not in getattr(runner, 'consumed_options', ()):
+            print(f"Warning: {plan.selection.reference.name} does not implement an "
+                  f"'output' option; nothing was written to {args.output}")
```

Either way `docs/CLI.md` should stop promising artifacts for SDKs that do not
write them, or the promise should be made true by the host.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: `evaluate` writes nothing for a third-party evaluation SDK.

Self-contained. No credentials, no network, no Docker, no model calls.

    pip install -e /path/to/AgentBehaviorBench
    python repro_evaluate_discards_result.py

docs/CLI.md states "Raw artifacts are saved even without the suite --output
option". That holds only for the built-in KUMA adapter, which persists its own
files. `evaluate` itself prints one line and drops the BenchmarkResult; its
--output flag is merely forwarded into the selected SDK's options, so an SDK
that does not implement an `output` option leaves nothing on disk.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GRAPH_PY = '''\
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


def echo(state: State) -> dict:
    return {"text": state["text"].upper()}


builder = StateGraph(State)
builder.add_node("echo", echo)
builder.add_edge(START, "echo")
builder.add_edge("echo", END)
graph = builder.compile()
'''

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "echo-agent"
display_name = "Echo"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''

REGISTRY_TOML = '''\
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "echo-agent"
path = "resources/agents/echo-agent"
enabled = true
status = "ready"
framework = "langgraph"
source = "local"
case = 1
'''

# A third-party SDK: implements exactly the documented create_run() contract and
# nothing else. It has no `output` option, like any evaluator that is not KUMA.
STUB_SDK_PY = '''\
from uuid import uuid4


class Input:
    def __init__(self, input_id, payload):
        self.input_id, self.payload = input_id, payload


class Report:
    def __init__(self, status):
        self.status, self.confidence = status, 1.0
        self.issues, self.evidence_gaps = (), ()


class Run:
    def __init__(self):
        self.run_id = f"stub_{uuid4().hex[:8]}"
        self.state, self.report, self.history = "ready", None, ()
        self._pending = True

    def get_input(self, *, full=False):
        if not self._pending:
            return None
        self.state = "input_delivered"
        return Input("only", "hello")

    def submit(self, output=None, *, status="completed", error=None):
        self._pending = False
        self.history = ({"input_id": "only", "output": output, "status": status},)
        self.report = Report("pass" if output == "HELLO" else "issue")
        self.state = "report_ready"
        return self.report


def create_run(*, repo_path, **_):
    del repo_path
    return Run()
'''


def build_workspace(root: Path) -> Path:
    unit = root / "resources" / "agents" / "echo-agent"
    (unit / "agent").mkdir(parents=True)
    (unit / "agent" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "./graph.py:graph"}}), encoding="utf-8"
    )
    (unit / "agent.toml").write_text(AGENT_TOML, encoding="utf-8")
    (unit / "requirement.md").write_text("# Uppercase the input.\n", encoding="utf-8")
    (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (root / "resources" / "registry.toml").write_text(REGISTRY_TOML, encoding="utf-8")
    (root / "stub_sdk.py").write_text(STUB_SDK_PY, encoding="utf-8")
    return root / "resources" / "registry.toml"


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="abb-evaluate-repro-"))
    registry = build_workspace(root)
    output = root / "requested-result.json"
    print(f"workspace: {root}")
    print(f"--output : {output}\n")

    env = dict(os.environ, PYTHONPATH=str(root))
    proc = subprocess.run(
        [sys.executable, "-m", "agentbench", "evaluate", "echo-agent",
         "--registry", str(registry),
         "--sdk", "python:stub_sdk",
         "--output", str(output)],
        capture_output=True, text=True, check=False, env=env,
    )

    print("=" * 72)
    print("A. `agentbench evaluate ... --output requested-result.json`")
    print("=" * 72)
    print(f"  exit code: {proc.returncode}")
    for line in (proc.stdout + proc.stderr).strip().splitlines():
        print(f"  {line}")
    print()

    print("=" * 72)
    print("B. What landed on disk")
    print("=" * 72)
    print(f"  --output path exists: {output.exists()}")
    written = sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix == ".json" and "resources" not in p.parts
    )
    print(f"  json files outside the Agent unit: {[p.name for p in written]}\n")

    print("=" * 72)
    print("C. The result the command already had in hand")
    print("=" * 72)
    from agentbench.cli.features import evaluate as evaluate_feature

    source = inspect.getsource(evaluate_feature.execute)
    for line in source.splitlines():
        if "runner.run(" in line or "result.report" in line or "options[name]" in line:
            print(f"  {line.strip()}")
    print()

    reproduced = proc.returncode == 0 and not output.exists() and not written
    if reproduced:
        print(
            "RESULT: reproduced — the run completed, a Judge report was produced,\n"
            "        and the BenchmarkResult was discarded without being written."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
workspace: /tmp/abb-evaluate-repro-xw6x132i
--output : /tmp/abb-evaluate-repro-xw6x132i/requested-result.json

========================================================================
A. `agentbench evaluate ... --output requested-result.json`
========================================================================
  exit code: 0
  Evaluation: one Case using stub_sdk; selected services may incur charges.
  Judge: pass

========================================================================
B. What landed on disk
========================================================================
  --output path exists: False
  json files outside the Agent unit: []

========================================================================
C. The result the command already had in hand
========================================================================
  options[name] = value
  result = runner.run(agent)
  if result.report is None:
  print(f'Judge: {result.report.status}')

RESULT: reproduced — the run completed, a Judge report was produced,
        and the BenchmarkResult was discarded without being written.
```

</details>

---

## 7. [observe] In-process runs emit no artifact_directory, leaving four of the viewer's five tabs empty with no explanation

### Summary

A host-side benchmark run — `runtime.type = "in_process"` — emits
`artifact_directory: null` on every progress event and writes no observe run
directory. Four of the trace viewer's five tabs are backed by
`SuiteRunCatalogAPI`, which enumerates runs from those directories, so they are
empty for every in-process Agent:

```
GET /api/observe/runs -> {"runs": [], "default_run": null}
```

The run itself passes and produces a Judge report. Only "Suite 进度" has anything
to show; "OTel 调用树", "Case / SDK / Judge", "交互时间线" and "执行流程 · 原型"
are blank, with no indication that this is expected rather than broken.

### Environment

- AgentBehaviorBench `e87bf3e`
- Python 3.12.3; no credentials, no Docker, no model calls

### Root cause

The evidence files the viewer reads — `framework.jsonl`, `network.jsonl`,
`otel.jsonl`, `otel-live.jsonl`, `otel-payloads/` — are all written by
`agentbench/runtime/agentcontainer/worker.py`, which only runs inside a
container:

```python
    store = TraceStore(output / "framework.jsonl", envelope.get("session_id", run_id),
                       source="framework", context=context)
```

and by `agentbench/observe/service.py`, which refuses anything else outright:

```python
def observe(agent, value, *, output: Path, environ, timeout=None):
    if runtime_type(agent.path) != "docker" or execution_strategy(agent.path) != "oneshot":
        raise ValueError("Observe currently requires runtime.type=docker and execution=oneshot; ...")
```

The host path in `agentbench/harness/runner/benchmark_runner.py` never sets an
artifact directory, so `BenchmarkProgress.artifact_directory` stays `None` and
`SuiteRunCatalogAPI.entries()` finds nothing to enumerate:

```python
        for agent_id, value in references:
            if agent_id not in selected or not isinstance(value, str):
                continue
```

`agentbench/adapter/langgraph/adapter.py` accepts a `run_config`, and the
container worker already builds the same observer callbacks the host could:

```python
        from agentbench.observe.observers import DEFAULT_OBSERVERS
        callbacks = DEFAULT_OBSERVERS.callbacks(descriptor.framework, store)
        if callbacks:
            config["callbacks"] = callbacks
```

so the framework half of the evidence is reachable from the host with no
container. Only the interceptor half genuinely needs Docker.

### Impact

- The observability story is tied to Docker. An Agent developed in-process — the
  fast iteration mode — produces a passing run with no inspectable trace.
- Nothing tells the user why. The tabs render empty, exactly as they would if the
  evidence had been lost, which is indistinguishable from a real defect. This is
  the failure mode `docs/observe/README.md` is otherwise careful about, where
  unlinkable requests are explicitly marked `uncorrelated` rather than hidden.

### Suggested fix

Two parts, and either is useful on its own.

**1. Emit framework evidence from the host path.** Give `BenchmarkRunner` an
artifact root, attach the same observers the container worker attaches, and
publish the directory on the progress events so `SuiteRunCatalogAPI` can find it.

```diff
--- a/agentbench/harness/runner/benchmark_runner.py
+++ b/agentbench/harness/runner/benchmark_runner.py
@@
+from agentbench.observe.observers import DEFAULT_OBSERVERS
+from agentbench.observe.store import TraceStore, atomic_json
@@
         run_config = {"configurable": {"thread_id": sdk_run.run_id}}
+        if self._artifact_root is not None:
+            directory = self._artifact_root / sdk_run.run_id
+            directory.mkdir(parents=True, exist_ok=True)
+            store = TraceStore(directory / "framework.jsonl", sdk_run.run_id,
+                               source="framework",
+                               context={"agent_id": registration.agent_id})
+            callbacks = DEFAULT_OBSERVERS.callbacks(registration.framework, store)
+            if callbacks:
+                run_config["callbacks"] = callbacks
+            atomic_json(directory / "run.json", {
+                "schema": "abb.evaluate.run.v1", "run_id": sdk_run.run_id,
+                "agent_id": registration.agent_id, "status": "running",
+            })
```

and set `artifact_directory=str(directory)` on the `benchmark_execution`
progress events so the existing catalog picks it up unchanged.

**2. Until then, say so in the UI.** When `/api/observe/runs` is empty because the
run was host-side, the evidence tabs should render a sentence explaining that
in-process runs do not produce trace artifacts and that `runtime.type = "docker"`
is required, rather than an empty panel. `docs/CLI.md` should carry the same
caveat next to the viewer description.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: a host-side benchmark run produces no observable evidence.

Self-contained. No credentials, no network, no Docker, no model calls.

    pip install -e /path/to/AgentBehaviorBench
    python repro_host_run_no_observe.py

An Agent with runtime.type = "in_process" runs through the host path, which
emits no artifact_directory on any progress event. The viewer's four evidence
tabs (OTel call tree, Case/SDK/Judge, interaction timeline, execution flow) are
all backed by SuiteRunCatalogAPI, which enumerates runs from those directories,
so they are empty for every host-side run. Only the Suite progress tab has data.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

GRAPH_PY = '''\
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


def echo(state: State) -> dict:
    return {"text": state["text"].upper()}


builder = StateGraph(State)
builder.add_node("echo", echo)
builder.add_edge(START, "echo")
builder.add_edge("echo", END)
graph = builder.compile()
'''

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "echo-agent"
display_name = "Echo"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''

REGISTRY_TOML = '''\
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "echo-agent"
path = "resources/agents/echo-agent"
enabled = true
status = "adapting"
framework = "langgraph"
source = "local"
case = 1
'''


class Input:
    def __init__(self, input_id, payload):
        self.input_id, self.payload = input_id, payload


class Report:
    def __init__(self, status):
        self.status, self.confidence = status, 1.0
        self.issues, self.evidence_gaps = (), ()


class Run:
    def __init__(self):
        self.run_id = f"repro_{uuid4().hex[:8]}"
        self.state, self.report, self.history = "ready", None, ()
        self._pending = True

    def get_input(self, *, full=False):
        if not self._pending:
            return None
        self.state = "input_delivered"
        return Input("only", "hello")

    def submit(self, output=None, *, status="completed", error=None):
        self._pending = False
        self.history = ({"input_id": "only", "output": output, "status": status},)
        self.report = Report("pass" if output == "HELLO" else "issue")
        self.state = "report_ready"
        return self.report


def create_run(*, repo_path, **_):
    del repo_path
    return Run()


def build_workspace(root: Path) -> Path:
    unit = root / "resources" / "agents" / "echo-agent"
    (unit / "agent").mkdir(parents=True)
    (unit / "agent" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "./graph.py:graph"}}), encoding="utf-8"
    )
    (unit / "agent.toml").write_text(AGENT_TOML, encoding="utf-8")
    (unit / "requirement.md").write_text("# Uppercase the input.\n", encoding="utf-8")
    (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (root / "resources" / "registry.toml").write_text(REGISTRY_TOML, encoding="utf-8")
    return root / "resources" / "registry.toml"


def main() -> int:
    import sys

    from agentbench.cli.features.certify import certify

    root = Path(tempfile.mkdtemp(prefix="abb-hostrun-repro-"))
    registry = build_workspace(root)
    artifact_base = root / "certified"
    print(f"workspace: {root}\n")

    print("=" * 72)
    print("A. A complete, passing host-side run")
    print("=" * 72)
    lines: list[str] = []
    code = certify("echo-agent", registry_path=registry, output_path=artifact_base,
                   sdk=sys.modules[__name__], output_fn=lines.append)
    for line in lines:
        if line.strip():
            print(f"  {line}")
    print(f"  certify exit code: {code}\n")

    snapshots = sorted(root.glob("certified-*.json"))
    events = json.loads(snapshots[-1].read_text(encoding="utf-8"))
    print("=" * 72)
    print("B. artifact_directory on every progress event")
    print("=" * 72)
    directories = []
    for event in events:
        if event.get("event") == "progress":
            directories.append(event.get("artifact_directory"))
            print(f"  stage={event.get('stage'):<20} artifact_directory={event.get('artifact_directory')}")
    print()

    print("=" * 72)
    print("C. What the viewer's evidence tabs can enumerate")
    print("=" * 72)
    from agentbench.observe.view_api import SuiteRunCatalogAPI

    catalog = SuiteRunCatalogAPI(snapshots[-1])
    listing = catalog.route("/api/observe/runs", {})
    print(f"  GET /api/observe/runs -> {json.dumps(listing)}")
    print("  tabs backed by this endpoint: OTel call tree, Case/SDK/Judge,")
    print("                                interaction timeline, execution flow\n")

    if code == 0 and set(directories) == {None} and listing["runs"] == []:
        print(
            "RESULT: reproduced — the run passed and produced a Judge report, yet\n"
            "        four of the viewer's five tabs have nothing to show."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
workspace: /tmp/abb-hostrun-repro-q9626poq

========================================================================
A. A complete, passing host-side run
========================================================================
  Certifying adapting Agent: echo-agent
  The registry will change to ready if the Agent completes its Cases without invocation errors.
  Suite ID: suite_b18529c8631a49449e36ead05fd04cfd
  Result artifact started: /tmp/abb-hostrun-repro-q9626poq/certified-20260910-050253.json
  Checking evaluation SDK configuration...
    OK | Provider mode: custom

------------------------------------------------------------------------------
  Running: [1/1] echo-agent
  Starting Agent...
    OK | LangGraphAdapter
  Generating Case from the selected SDK...
    OK | run=repro_c4433ac0
  Running Agent inputs and SDK Judge...
    OK | Judge: pass
  Result: PASS | cases=1/1

Suite complete: 1 passed, 0 failed, 0 skipped, 1 selected.
  + RESULT VIEWER -------------------------------------------------------------+
  | Result saved: /tmp/abb-hostrun-repro-q9626poq/certified-20260910-050253.json|
  | Open later: python -m agentbench view /tmp/abb-hostrun-repro-q9626poq/certified-20260910-050253.json|
  +----------------------------------------------------------------------------+
  Certification passed. Agent 'echo-agent' is now ready.
  certify exit code: 0

========================================================================
B. artifact_directory on every progress event
========================================================================
  stage=sdk_check            artifact_directory=None
  stage=sdk_check            artifact_directory=None
  stage=agent_start          artifact_directory=None
  stage=agent_start          artifact_directory=None
  stage=case_generation      artifact_directory=None
  stage=case_generation      artifact_directory=None
  stage=benchmark_execution  artifact_directory=None
  stage=benchmark_execution  artifact_directory=None

========================================================================
C. What the viewer's evidence tabs can enumerate
========================================================================
  GET /api/observe/runs -> {"runs": [], "default_run": null}
  tabs backed by this endpoint: OTel call tree, Case/SDK/Judge,
                                interaction timeline, execution flow

RESULT: reproduced — the run passed and produced a Judge report, yet
        four of the viewer's five tabs have nothing to show.
```

</details>

---

## 8. [viewer] `agentbench view` returns 503 on a fresh clone: web/dist is gitignored and the build step is undocumented

### Summary

On a fresh clone, the viewer the CLI tells you to use answers 503:

```
Error code: 503
Message: Trace UI not built. Run npm install and npm run build in web/..
```

`cli/viewer.py` serves the UI from `<repo>/web/dist`, and `web/.gitignore`
ignores `dist/`, so a clone never has it. `certify` and `run` print
`Open later: python -m agentbench view <path>` on completion with no mention of
the build step, and `README.md` does not mention `web/` at all. The error message
itself is the only place the requirement appears, and you only see it after the
run is over.

### Environment

- AgentBehaviorBench `e87bf3e`, fresh `git clone`
- node 26.5.0, npm 12.0.2, Python 3.12.3
- `npm ci && npm run build` in `web/` fixes it (vite 7.3.6, 1961 modules, 3.1s)

### Root cause

`agentbench/cli/viewer.py:16`:

```python
WEB_ROOT = Path(__file__).resolve().parents[2] / "web" / "dist"
```

`web/.gitignore`:

```
node_modules/
dist/
.env*
```

`git ls-files web/dist` returns nothing, so `WEB_ROOT` never exists in a clone.

`agentbench/cli/viewer.py:152-158` then refuses to serve:

```python
            suite_path = _suite_view_path(expected_suite_id)
            if parsed.path.rstrip("/") == suite_path.rstrip("/"):
                index = WEB_ROOT / "index.html"
                if not index.is_file():
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE,
                                    "Trace UI not built. Run npm install and npm run build in web/.")
                    return
```

Note the data API is fine — `/api/suites/<id>/result` returns the full snapshot.
Only the UI is missing, so the failure looks like a broken viewer rather than a
missing build.

### Impact

The first end-to-end experience is: run `certify`, watch it pass, follow the
command it prints, get a 503. Nothing in `README.md`, `docs/CLI.md`'s viewer
section, or the CLI output says a JavaScript build is required first.

`docs/CLI.md` even advertises the no-Node path in a way that reads as if no Node
were needed at all:

> Open a saved observe/evaluation run without Node.js using
> `python -m agentbench view results/observe/<run_id>/run.json`.

That is true for the *runtime* — the Python server serves prebuilt assets — but
the assets still have to be built by Node once.

### Suggested fix

Any one of these closes it; the first is the smallest.

1. Tell the user at the point of failure and at the point of advertisement:

```diff
--- a/agentbench/cli/viewer.py
+++ b/agentbench/cli/viewer.py
@@
                 index = WEB_ROOT / "index.html"
                 if not index.is_file():
                     self.send_error(HTTPStatus.SERVICE_UNAVAILABLE,
-                                    "Trace UI not built. Run npm install and npm run build in web/.")
+                                    f"Trace UI not built. Run: cd {WEB_ROOT.parent} "
+                                    f"&& npm ci && npm run build")
                     return
```

```diff
--- a/agentbench/cli/viewer.py
+++ b/agentbench/cli/viewer.py
@@ def serve_result_log(...)
+    if not (WEB_ROOT / "index.html").is_file():
+        print(f"Trace UI not built; run: cd {WEB_ROOT.parent} && npm ci && npm run build")
```

and make `certify`/`run` print the build hint alongside the `Open later:` line
when `WEB_ROOT/index.html` is absent.

2. Document it: one line in `README.md` under Setup, and in `docs/CLI.md` beside
   the "without Node.js" sentence.

3. Or build on demand: if `npm` is on PATH and `web/dist` is missing, run
   `npm ci && npm run build` once and say so. Convenient, but it makes a CLI
   command shell out to a package manager, so 1 + 2 may be preferable.

### Note on the reproduction script

The machine that runs the script has usually already built `web/dist`, so the
script reports the current state and then points `WEB_ROOT` at an empty directory
to recreate exactly the fresh-clone condition. The `git ls-files web/dist` count
in section A is the part that shows a clone can never have it.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: `agentbench view` returns 503 on a fresh clone.

Self-contained. No credentials, no network access, no Docker.

    pip install -e /path/to/AgentBehaviorBench
    python repro_viewer_not_built.py

cli/viewer.py serves the trace UI from <repo>/web/dist, and web/.gitignore
ignores dist/. A fresh clone therefore has no UI, and `agentbench view` — which
`certify` and `run` print as the way to open a result — answers 503. Nothing in
the CLI output mentions the npm build step.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from threading import Thread


def main() -> int:
    from agentbench.cli import viewer as viewer_module

    web_root = viewer_module.WEB_ROOT
    repo = web_root.parents[1]
    print("=" * 72)
    print("A. Where the UI is served from, and whether it is committed")
    print("=" * 72)
    print(f"  cli/viewer.py WEB_ROOT      : {web_root}")
    print(f"  WEB_ROOT/index.html present : {(web_root / 'index.html').is_file()}")
    ignored = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "-v", "web/dist"],
        capture_output=True, text=True, check=False,
    )
    print(f"  git check-ignore web/dist   : {ignored.stdout.strip() or '(not ignored)'}")
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "web/dist"],
        capture_output=True, text=True, check=False,
    )
    print(f"  files tracked under web/dist: {len(tracked.stdout.split())}\n")

    print("=" * 72)
    print("B. Serving a result with WEB_ROOT in its fresh-clone state (absent)")
    print("=" * 72)
    workspace = Path(tempfile.mkdtemp(prefix="abb-viewer-repro-"))
    suite_id = "suite_reprodemo"
    result_log = workspace / "result.json"
    result_log.write_text(json.dumps([
        {"event": "run_started", "source": "abb", "suite_id": suite_id,
         "timestamp": "2026-01-01T00:00:00+00:00", "selected_agent_ids": ["demo"]},
        {"event": "suite_completed", "source": "abb", "suite_id": suite_id,
         "timestamp": "2026-01-01T00:00:01+00:00",
         "summary": {"selected": 1, "attempted": 1, "passed": 1,
                     "failed": 0, "skipped": 0, "suite_passed": True}},
    ]), encoding="utf-8")

    # A fresh clone has no web/dist at all; point WEB_ROOT at an empty directory.
    viewer_module.WEB_ROOT = workspace / "never-built"
    server = viewer_module.create_viewer_server(result_log, host="127.0.0.1", port=0)
    Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[0], server.server_address[1]
    url = f"http://{host}:{port}/suite/{suite_id}/"
    print(f"  GET {url}")
    status, body = None, ""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status, body = response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read().decode("utf-8", "replace")
    finally:
        server.shutdown()
    print(f"  status: {status}")
    for line in body.splitlines():
        if "Message:" in line or "Error code:" in line:
            print(f"  {line.strip()}")
    print()

    print("=" * 72)
    print("C. What `certify` tells the user after a run")
    print("=" * 72)
    print("  Result saved: <path>/certify-<timestamp>.json")
    print("  Open later: python -m agentbench view <path>/certify-<timestamp>.json")
    print("  (no mention of `npm ci && npm run build` in web/)\n")

    if status == 503 and "not built" in body.lower():
        print(
            "RESULT: reproduced — the viewer the CLI advertises answers 503 until\n"
            "        the user independently discovers the npm build step."
        )
        return 0
    print(f"RESULT: not reproduced (status={status})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
========================================================================
A. Where the UI is served from, and whether it is committed
========================================================================
  cli/viewer.py WEB_ROOT      : /home/wy/projects/DefuzeX/AgentBehaviorBench/web/dist
  WEB_ROOT/index.html present : True
  git check-ignore web/dist   : web/.gitignore:2:dist/	web/dist
  files tracked under web/dist: 0

========================================================================
B. Serving a result with WEB_ROOT in its fresh-clone state (absent)
========================================================================
  GET http://127.0.0.1:40213/suite/suite_reprodemo/
  status: 503
  <p>Error code: 503</p>
  <p>Message: Trace UI not built. Run npm install and npm run build in web/..</p>

========================================================================
C. What `certify` tells the user after a run
========================================================================
  Result saved: <path>/certify-<timestamp>.json
  Open later: python -m agentbench view <path>/certify-<timestamp>.json
  (no mention of `npm ci && npm run build` in web/)

RESULT: reproduced — the viewer the CLI advertises answers 503 until
        the user independently discovers the npm build step.
```

</details>

---

## 9. [registry] Bundled registry marks company-research-agent ready, contradicting docs/Agents/Layout.md and its own tests

### Summary

The shipped `resources/registry.toml` marks `company-research-agent` as `ready`,
which puts it in `agentbench run`'s default set. Two other places in the same
repository say it should be `adapting`:

- `docs/Agents/Layout.md:68` — "so status stays `adapting`. Image build, real
  research, full model routing and cross-process OTel collection have not been
  validated by this layout migration."
- `tests/test_registry.py` — `assert registry.ready() == ()`

`python -m pytest tests/test_registry.py` fails on a clean checkout: 2 failed,
11 passed.

### Environment

- AgentBehaviorBench `e87bf3e`, clean checkout, no local edits
- Python 3.12.3, pytest with the `[otel]` extra installed

### Root cause

`resources/registry.toml`:

```toml
[[agents]]
agent_id = "company-research-agent"
path = "resources/agents/01-company-research-agent"
enabled = true
status = "ready"
framework = "langgraph"
source = "https://github.com/guy-hartstein/company-research-agent"
case = 1
```

`tests/test_registry.py`:

```python
def test_ready_agents_are_the_default_runnable_subset() -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

    assert registry.ready() == ()
    assert {agent.agent_id for agent in registry.enabled()} == {"company-research-agent"}
    assert {path.name for path in (REPO_ROOT / "resources" / "agents").iterdir() if path.is_dir()} == {
        "01-company-research-agent",
    }
    assert {agent.agent_id for agent in registry.enabled_with_status("adapting")} == {
        "company-research-agent",
    }
```

Two failures follow:

```
FAILED tests/test_registry.py::test_registry_resolves_registered_agents[company-research-agent-01-company-research-agent-True-adapting-1]
  - AssertionError: assert 'ready' == 'adapting'
FAILED tests/test_registry.py::test_ready_agents_are_the_default_runnable_subset
  - AssertionError: assert (AgentRegistr...rement.md')),) == ()
```

The second test also asserts `resources/agents/` contains exactly
`01-company-research-agent`, but the repository now ships a second directory:

```
resources/agents/ contains: ['01-company-research-agent', '02-deer-flow']
```

`02-deer-flow` has only `agent/` and a `README.md` — no `agent.toml`, no
`Dockerfile`, no `requirement.md` — and is not in the registry, so it is not
registrable as it stands.

### Impact

- `agentbench run` executes enabled + ready Agents. As shipped it will try to run
  an Agent that the documentation states has unvalidated image build, model
  routing and OTel collection. On native Linux Docker it will not get that far
  anyway, but on Docker Desktop it will.
- A clean checkout has a red test suite, so a contributor cannot tell their own
  change from the pre-existing failure.
- `certify` exists precisely to make this transition, and it rewrites the status
  itself, so a `ready` value committed by hand bypasses the mechanism the design
  provides.

### Suggested fix

Pick whichever matches the intent; the first matches the documentation.

**1. The registry is wrong** — restore `adapting` and let `certify` promote it:

```diff
--- a/resources/registry.toml
+++ b/resources/registry.toml
@@
 agent_id = "company-research-agent"
 path = "resources/agents/01-company-research-agent"
 enabled = true
-status = "ready"
+status = "adapting"
 framework = "langgraph"
```

**2. The Agent really is certified** — then update the doc and the tests
together, and record what validated it:

```diff
--- a/docs/Agents/Layout.md
+++ b/docs/Agents/Layout.md
@@
-image. The native service launch, HTTP caller and model routes remain unconfigured,
-so status stays `adapting`. Image build, real research, full model routing and
-cross-process OTel collection have not been validated by this layout migration.
+image. Image build, real research, model routing and cross-process OTel
+collection were validated on <date>, so the registry status is `ready`.
```

```diff
--- a/tests/test_registry.py
+++ b/tests/test_registry.py
@@
-    assert registry.ready() == ()
+    assert {agent.agent_id for agent in registry.ready()} == {"company-research-agent"}
```

Either way, `02-deer-flow` needs handling: complete it into a registrable unit
(`agent.toml`, `requirement.md`, `Dockerfile`) and register it as `adapting`, or
move it out of `resources/agents/` until it is one. The directory-set assertion
in `test_ready_agents_are_the_default_runnable_subset` should then be relaxed to
"every directory here is registered", which is the property actually worth
holding.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: the bundled registry contradicts its own tests and docs.

Self-contained. No credentials, no network, no Docker.

    pip install -e /path/to/AgentBehaviorBench
    python repro_registry_status.py

resources/registry.toml marks company-research-agent `ready`, so `agentbench run`
will execute it. docs/Agents/Layout.md says its status stays `adapting` because
image build, real research, model routing and cross-process OTel collection have
not been validated, and tests/test_registry.py asserts registry.ready() == ().

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    import agentbench
    from agentbench.harness import load_registry

    repo = Path(agentbench.__file__).resolve().parents[1]
    registry_path = repo / "resources" / "registry.toml"

    print("=" * 72)
    print("A. resources/registry.toml as shipped")
    print("=" * 72)
    registry = load_registry(registry_path)
    for agent in registry.enabled():
        print(f"  {agent.agent_id:<26} status={agent.status}")
    ready = [a.agent_id for a in registry.ready()]
    print(f"  registry.ready() -> {ready}\n")

    print("=" * 72)
    print("B. docs/Agents/Layout.md")
    print("=" * 72)
    layout = (repo / "docs" / "Agents" / "Layout.md").read_text(encoding="utf-8")
    for number, line in enumerate(layout.splitlines(), 1):
        if "status stays" in line:
            start = max(0, number - 4)
            for offset, context in enumerate(layout.splitlines()[start:number], start + 1):
                print(f"  {offset}: {context}")
    print()

    print("=" * 72)
    print("C. tests/test_registry.py")
    print("=" * 72)
    test_source = (repo / "tests" / "test_registry.py").read_text(encoding="utf-8")
    block = re.search(
        r"def test_ready_agents_are_the_default_runnable_subset.*?(?=\n\ndef |\Z)",
        test_source, re.S,
    )
    if block:
        for line in block.group(0).strip().splitlines():
            print(f"  {line}")
    print()

    print("=" * 72)
    print("D. The suite as it runs today")
    print("=" * 72)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_registry.py"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    for line in proc.stdout.strip().splitlines()[-6:]:
        print(f"  {line}")
    print()

    agents_dir = {p.name for p in (repo / "resources" / "agents").iterdir() if p.is_dir()}
    print(f"  resources/agents/ contains: {sorted(agents_dir)}")
    print("  (the same test asserts this set is exactly {'01-company-research-agent'})\n")

    if ready and "status stays `adapting`" in layout and proc.returncode != 0:
        print(
            "RESULT: reproduced — the shipped registry promotes an Agent that the\n"
            "        documentation calls unvalidated and the test suite expects to\n"
            "        be adapting, so `agentbench run` would execute it."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
========================================================================
A. resources/registry.toml as shipped
========================================================================
  company-research-agent     status=ready
  registry.ready() -> ['company-research-agent']

========================================================================
B. docs/Agents/Layout.md
========================================================================
  65: The original GitHub checkout has been relocated unchanged into `agent/`.
  66: Its outer manifest selects Docker, and its outer Dockerfile describes a backend
  67: image. The native service launch, HTTP caller and model routes remain unconfigured,
  68: so status stays `adapting`. Image build, real research, full model routing and

========================================================================
C. tests/test_registry.py
========================================================================
  def test_ready_agents_are_the_default_runnable_subset() -> None:
      registry = load_registry(REPO_ROOT / "resources" / "registry.toml")

      assert registry.ready() == ()
      assert {agent.agent_id for agent in registry.enabled()} == {"company-research-agent"}
      assert {path.name for path in (REPO_ROOT / "resources" / "agents").iterdir() if path.is_dir()} == {
          "01-company-research-agent",
      }
      assert {agent.agent_id for agent in registry.enabled_with_status("adapting")} == {
          "company-research-agent",
      }

========================================================================
D. The suite as it runs today
========================================================================

  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
  =========================== short test summary info ============================
  FAILED tests/test_registry.py::test_registry_resolves_registered_agents[company-research-agent-01-company-research-agent-True-adapting-1] - AssertionError: assert 'ready' == 'adapting'
  FAILED tests/test_registry.py::test_ready_agents_are_the_default_runnable_subset - AssertionError: assert (AgentRegistr...rement.md')),) == ()
  2 failed, 11 passed, 1 warning in 0.09s

  resources/agents/ contains: ['01-company-research-agent', '02-deer-flow']
  (the same test asserts this set is exactly {'01-company-research-agent'})

RESULT: reproduced — the shipped registry promotes an Agent that the
        documentation calls unvalidated and the test suite expects to
        be adapting, so `agentbench run` would execute it.
```

</details>

---

## 10. [registry] A Dockerfile is required from Agents whose runtime.type is in_process and which are never containerised

### Summary

`load_registry` refuses to register an Agent that has no `Dockerfile`, even when
its manifest says `runtime.type = "in_process"` and it will never be
containerised:

```
FileNotFoundError: Agent Dockerfile does not exist: .../resources/agents/in-process-only/Dockerfile
```

Adding an empty one-line `Dockerfile` next to the manifest makes registration
succeed. The file is then never read by anything.

### Environment

- AgentBehaviorBench `e87bf3e`
- Python 3.12.3; no credentials, no Docker, no model calls

### Root cause

`agentbench/harness/registry.py:104-107` validates unconditionally:

```python
    dockerfile = agent_path / "Dockerfile"
    if not dockerfile.is_file():
        raise FileNotFoundError(f"Agent Dockerfile does not exist: {dockerfile}")
```

The manifest has already been parsed at that point (`manifest` is in scope from
line 94), so `runtime.type` is available.

`agentbench/runtime/factory.py:32-42` shows the file is irrelevant for
`in_process`:

```python
        selected = runtime_type(agent.path)
        if selected == "in_process":
            return adapter_factory.create(agent)
        if selected == "docker":
            return ContainerAgentAdapter(
                agent, self._docker_builder(), caller=self._container_caller
            )
```

`docs/Agents/Layout.md` documents the Dockerfile as part of the unit layout, but
also documents `in_process` as a first-class runtime in the same file:

```text
CLI or Python caller → load_registry → user-named outer directory
  → agent.toml → runtime.type
      → docker: outer Dockerfile + agent/ → image → launch.argv
      → in_process: agent/langgraph.json → agent/<entrypoint> → graph
```

so the two are inconsistent about whether the file is required.

### Impact

Minor, but it is a wrong signal at the first step of onboarding: the author of a
pure in-process Agent is told a Docker artifact is missing, and the only way
forward is to create a placeholder that nothing consumes. It also makes the
registry's validation errors less trustworthy, since one of them is not a real
requirement.

### Suggested fix

Validate the Dockerfile only for the runtime that uses it, and validate the
`launch`/`build` requirements for that runtime while you are there.

```diff
--- a/agentbench/harness/registry.py
+++ b/agentbench/harness/registry.py
@@
-    dockerfile = agent_path / "Dockerfile"
-    if not dockerfile.is_file():
-        raise FileNotFoundError(f"Agent Dockerfile does not exist: {dockerfile}")
+    runtime = manifest.get("runtime")
+    runtime_type = runtime.get("type", "docker") if isinstance(runtime, dict) else "docker"
+    if runtime_type == "docker":
+        build = manifest.get("build")
+        dockerfile_name = (
+            build.get("dockerfile", "Dockerfile") if isinstance(build, dict) else "Dockerfile"
+        )
+        dockerfile = agent_path / dockerfile_name
+        if not dockerfile.is_file():
+            raise FileNotFoundError(f"Agent Dockerfile does not exist: {dockerfile}")
```

Reading the name from `[build].dockerfile` also fixes a second, smaller
assumption: the manifest lets an Agent name its Dockerfile, but the registry
only ever looks for the literal `Dockerfile`.

`docs/Agents/Layout.md` would then mark the file as required for
`runtime.type = "docker"` rather than for every unit.

<details>
<summary><b>Reproduction script</b> — self-contained, exit code 0 means the defect still reproduces</summary>

```python
"""AgentBehaviorBench: registry demands a Dockerfile from an in_process Agent.

Self-contained. No credentials, no network, no Docker.

    pip install -e /path/to/AgentBehaviorBench
    python repro_dockerfile_required.py

Registers one Agent whose manifest says `runtime.type = "in_process"` — it will
never be containerised — and shows that load_registry() refuses it until an
unused Dockerfile is placed beside the manifest.

Exit code 0 means the defect still reproduces.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

AGENT_TOML = '''\
schema_version = "defuzex-bench.agent.v2"
agent_id = "in-process-only"
display_name = "In-process only"
framework = "langgraph"

[runtime]
type = "in_process"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "text"
output_key = "text"
'''

REGISTRY_TOML = '''\
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "in-process-only"
path = "resources/agents/in-process-only"
enabled = true
status = "adapting"
framework = "langgraph"
source = "local"
case = 1
'''

GRAPH_PY = '''\
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class State(TypedDict):
    text: str


def echo(state: State) -> dict:
    return {"text": state["text"]}


builder = StateGraph(State)
builder.add_node("echo", echo)
builder.add_edge(START, "echo")
builder.add_edge("echo", END)
graph = builder.compile()
'''


def build_workspace(root: Path, *, with_dockerfile: bool) -> Path:
    unit = root / "resources" / "agents" / "in-process-only"
    (unit / "agent").mkdir(parents=True, exist_ok=True)
    (unit / "agent" / "graph.py").write_text(GRAPH_PY, encoding="utf-8")
    (unit / "agent" / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": "./graph.py:graph"}}), encoding="utf-8"
    )
    (unit / "agent.toml").write_text(AGENT_TOML, encoding="utf-8")
    (unit / "requirement.md").write_text("# Echo the input text.\n", encoding="utf-8")
    if with_dockerfile:
        (unit / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    registry = root / "resources" / "registry.toml"
    registry.write_text(REGISTRY_TOML, encoding="utf-8")
    return registry


def main() -> int:
    from agentbench.harness import load_registry

    print("A. in_process Agent, no Dockerfile")
    root = Path(tempfile.mkdtemp(prefix="abb-dockerfile-repro-"))
    registry = build_workspace(root, with_dockerfile=False)
    missing_error = None
    try:
        load_registry(registry)
        print("   registered\n")
    except FileNotFoundError as exc:
        missing_error = exc
        print(f"   {type(exc).__name__}: {exc}\n")

    print("B. identical Agent, plus an unused Dockerfile")
    root2 = Path(tempfile.mkdtemp(prefix="abb-dockerfile-repro-"))
    registry2 = build_workspace(root2, with_dockerfile=True)
    agents = load_registry(registry2).enabled()
    print(f"   registered: {[a.agent_id for a in agents]}")
    print("   the Dockerfile is never read: runtime.type is in_process\n")

    if missing_error is not None and agents:
        print(
            "RESULT: reproduced — registry.py requires a Dockerfile from an Agent\n"
            "        that the runtime factory will never containerise."
        )
        return 0
    print("RESULT: not reproduced")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

<details>
<summary><b>Verbatim output</b> from the run recorded here</summary>


```
A. in_process Agent, no Dockerfile
   FileNotFoundError: Agent Dockerfile does not exist: /tmp/abb-dockerfile-repro-twkja9h5/resources/agents/in-process-only/Dockerfile

B. identical Agent, plus an unused Dockerfile
   registered: ['in-process-only']
   the Dockerfile is never read: runtime.type is in_process

RESULT: reproduced — registry.py requires a Dockerfile from an Agent
        that the runtime factory will never containerise.
```

</details>

---

## Suggested order of work

1. **#1 (`[docker]`)** — until this is fixed there is no interception on Linux,
   and interception is what produces the network evidence the whole Observe
   module and its viewer are built around. The patch is one line.
2. **#2 (`[benchmark_runner]`)** — `RunningAgent.ainvoke` is already written and
   already correct; it just has no caller. Connecting it makes the canonical
   LangGraph template runnable in-process.
3. **#3 (`[correlation]`)** — this is the difference between "we record two
   evidence streams" and "we can tell you which model call belongs to which
   step". Adding `httpx2` and `aiohttp` to the patch list is small.
4. **#5, #6 (`[cli]`, `[evaluate]`)** — both are about the promises the CLI
   already makes: a flag that exists in the Python API but not on the command
   line, and a flag that is accepted and then ignored.
5. **#4, #7, #8 (`[langgraph]`, `[observe]`, `[viewer]`)** — each turns a silent
   dead end into either a working path or an explicit message.
6. **#9, #10 (`[registry]`)** — housekeeping, but #9 leaves a clean checkout with
   a red test suite, which costs every future contributor a few minutes.

## A note on what this testing did *not* find

Several things worked exactly as documented and are worth saying out loud,
because they are what made the rest of this report possible:

- **The registry is genuinely relocatable.** `load_registry` derives the
  repository root from the registry file itself, so an entire Agent workspace can
  live outside the checkout. Every Agent in this report was registered that way,
  which is why the repository could stay read-only.
- **The SDK seam is real.** A substitute evaluation SDK — case generation,
  handshake, judging, ~200 lines, no credentials — drove the full benchmark
  without touching the harness. `while (test_input := sdk_run.get_input(...))`
  runs every input the SDK offers; the "one Case, one Input" limit is KUMA's, not
  the harness's.
- **The bindings escape hatch works.** The two LangGraph gaps in #2 and #4 were
  both worked around from a per-Agent `bindings/*.py` without editing upstream
  source. The complaint in those issues is that a binding is *required* for an
  ordinary Agent, not that the mechanism is missing.
- **The interaction timeline is good.** Once #1 was patched, the viewer showed
  the ReAct loop in full, and the `chat` entries named the *real* upstream model
  rather than the one the Agent believed it was calling. That specific property —
  being able to reconcile what an Agent claims with what actually left the
  container — is the most valuable thing here, and it is exactly what #3 is
  currently preventing from going further.
- **Nothing is fabricated.** Where evidence could not be linked, the code writes
  `null` instead of guessing from timestamps, matching this project's own stated
  rule that proximity in time is not a parent/child relationship. That honesty is
  why #3 is a clean bug report and not an argument.

# Choosing an evaluation SDK

AgentBench accepts a Python module or configured object through `sdk=...`.
The selected SDK owns Case generation, credentials, Providers and judging.
AgentBench owns Agent invocation and the existing suite/progress/result flow.

```python
import my_evaluation_sdk
from agentbench.harness import BenchmarkRunner, SuiteRunner, load_registry

registry = load_registry("resources/registry.toml")
agent = registry.find("langgraph-new-project", enabled_only=False)

result = BenchmarkRunner(
    sdk=my_evaluation_sdk,
    sdk_options={"difficulty": "bounded"},
).run(agent)

suite = SuiteRunner(
    sdk=my_evaluation_sdk,
    sdk_options={"difficulty": "bounded"},
).run([agent])
```

Each Case gets a fresh `sdk.create_run(repo_path=agent.path, **sdk_options)` call.
`repo_path` is reserved for the selected Agent. AgentBench copies the options
mapping and does not add DefuzeX keys or configuration to an injected SDK.
Configure a supplied `benchmark_runner` or `suite_runner` directly; combining
one with another `sdk`/`sdk_options` selection is rejected.

## Current interface

The structural protocols are exported from `agentbench.harness`:

| Object | Required interface |
| --- | --- |
| SDK | `create_run(**options)` returns a compatible Run |
| Run | `run_id`, `state`, `history`, `report` |
| Run | `get_input(full=True)` returns an Input or `None` |
| Input | `input_id`, `payload` |
| Run | `submit(output)` records the result and returns a report or `None` |
| Run | `submit(status="failed", error="...")` records an Agent failure |
| Report | `status`, `confidence`, `issues`, `evidence_gaps` |

`get_input()` must keep the current Input pending until submission. At the end,
it returns `None`. The SDK performs judging during submission or exposes the
finished report via `run.report`. AgentBench counts `status == "pass"` as a pass;
no report is not a pass. Existing progress and result exports retain this model.

SDKs with different method names, asynchronous APIs, or different result shapes
need a small user-owned adapter implementing this interface. This change does
not claim arbitrary SDK modules work without adaptation. A configured object
can retain SDK-specific state; do not pass an uninstantiated class.

## DefuzeX

The existing default and `run_defuzex()` / `validate_defuzex()` compatibility
entry points remain available. Their credential and Provider policy lives in
`agentbench/sdk/defuzex.py`. The SDK package is now optional:

```bash
python -m pip install -e ".[defuzex]"
```

Alternatively, install the local DefuzeX source checkout separately. To select
the real public module explicitly:

```python
import defuzex
from agentbench.harness import BenchmarkRunner

runner = BenchmarkRunner(
    sdk=defuzex,
    sdk_options={"requirement_path": "resources/agents/01-my-agent/requirement.md"},
)
result = runner.run(agent)
```

Explicit module injection forwards its options directly: supply the requirements
and other options your installed SDK version expects. It does not apply the
legacy Provider-pair policy, credential lookup or registered-requirement default.
The SDK itself may resolve its credentials from its supported environment.

**Execution placement has not changed.** This seam is in the current process;
it does not transfer a module/object into Docker. DefuzeX formal mode requires
the SDK and Agent in the same container. Host-side local development still
requires explicit `allow_local=True`; the existing default CLI preserves its
previous local-development settings. Container Worker migration and cross-process
OTel are separate work and are not certified by these interface tests.

## Offline example

`examples/local_sdk.py` is a complete deterministic evaluation SDK. It checks
exact equality with a published expected string and needs no credentials or
DefuzeX installation. From the repository root:

```python
from examples import local_sdk
from agentbench.harness import BenchmarkRunner, load_registry

agent = load_registry("resources/registry.toml").find(
    "langgraph-new-project", enabled_only=False,
)
result = BenchmarkRunner(sdk=local_sdk).run(agent)
print(result.report.status)  # pass
```

For CLI selection, see `CLI.md`. Python CLI callers can also pass
`sdk=local_sdk, sdk_options={...}` to `agentbench.cli.main.main`, the run feature
or the certify feature. Normal registry selection rules still apply.

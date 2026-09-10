# Choosing an evaluation SDK

AgentBench accepts a Python module or configured object through `sdk=...` and
discovers CLI plugins from the `defuzex_agentbench.evaluation_sdks` package
entry-point group. Both forms become the same immutable evaluation plan before
runner construction. The selected SDK owns Case generation, credentials,
Providers and judging. AgentBench owns Agent invocation and the existing
suite/progress/result flow.

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

## Installed CLI plugins

A PyPI distribution can give its SDK a stable CLI name:

```toml
[project.entry-points."defuzex_agentbench.evaluation_sdks"]
acme = "acme_evaluation:sdk"
```

After installation, inspect and select it without coupling scripts to a Python
module path:

```bash
agentbench sdk list
agentbench sdk show acme
agentbench run --sdk acme --sdk-options sdk-options.json
```

`sdk list` reads only installed package metadata. Selection loads only the
chosen entry point. Duplicate short names fail with the qualified alternatives;
use `DISTRIBUTION::NAME` to disambiguate them. `kuma` is reserved for the
built-in adapter, so an external plugin with that name also needs a distribution
qualifier. An entry point exposing the plain
`create_run()` interface executes host-side. A formal container plugin implements
`EvaluationSDKPlugin` and returns its `EvaluationRunner` Strategy. See
[Evaluation SDK plugin architecture](architecture/evaluation-sdk-plugins.md).

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

A plain `create_run()` module/object is local to the current process; ABB does
not pretend it can serialize an arbitrary Python value into Docker. The built-in
`kuma` plugin implements the formal container Strategy. Other formal plugins
must implement `EvaluationSDKPlugin` so their package owns runner construction
and deployment. The next migration step is a shared, versioned container worker
protocol for those formal plugins.

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

The equivalent explicit development CLI selection is:

```bash
agentbench run --sdk python:examples.local_sdk
```

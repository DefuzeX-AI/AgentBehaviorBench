# Directory-discovered evaluation SDKs

An evaluation SDK adapter supplies Cases and Judges Agent outputs. It is not
the tested Agent: Agents remain registered in `resources/registry.toml`.
SDK availability is determined solely by adapter packages under the installed
`agentbench/sdk/` directory, independently of the working directory.

## Package layout and discovery

```text
agentbench/sdk/
  contracts.py          # SDK interfaces and supported interface version
  discovery.py          # Filesystem discovery and selected-module import
  plugins.py            # Selection and execution plans
  runtime.py            # Runner construction
  common/               # Shared helpers, not an adapter
  <sdk_name>/
    __init__.py         # Empty is sufficient; keep it lightweight
    plugin.py           # Exports one adapter instance called plugin
    ...                 # SDK-specific dependencies, execution, result conversion
```

Only direct child directories containing `plugin.py` are candidates. Each
candidate must have `__init__.py` and a valid ASCII Python identifier as its
directory name. Private/hidden directories are ignored. Linked packages or
entry files and ambiguous case-insensitive names are rejected. Prefer lowercase
names with underscores. No recursive filesystem search or vendor name list is
used. Package files should come from trusted code: selecting an adapter executes
Python, so discovery is not a sandbox for downloaded plugins.

Discovery lists names without importing packages. It does not prove that SDK
dependencies, credentials, Docker, or remote services are ready. Only the chosen
adapter is imported; its execution environment is checked before Agent execution.
One broken dependency must not stop listing or selecting another adapter. Invalid
package structure is reported instead of silently hiding a candidate.

No adapters means an actionable configuration error. One is selected by default.
Multiple adapters require an explicit name; ABB never selects the first directory
or runs all adapters just because a folder was added. New directories are seen on
the next discovery call, but editing loaded Python code requires a process restart.

## Adapter interface

Export an instance, not a class. The directory supplies the name; the adapter
does not need a duplicate `name` field.

```python
from agentbench.sdk.contracts import SDK_PLUGIN_API_VERSION


class Adapter:
    api_version = SDK_PLUGIN_API_VERSION
    execution = "local"  # Or "container"; the adapter owns actual deployment.

    def create_benchmark_runner(self, *, context, options):
        from .runner import Runner
        return Runner(context=context, options=options)


plugin = Adapter()
```

`context` provides the environment, optional model, trace sink, and trace size
limit. `options` is a shallow defensive copy exposed as a read-only mapping.
Each adapter owns its defaults and rejects unsupported options. Do not initialize
clients, read credentials, contact services, or start Docker at module import.

The returned runner implements the existing `EvaluationRunner` interface:

- `validate_sdk(registration) -> str`: check prerequisites without running the
  Agent or creating a paid Case; return a descriptive execution mode.
- `run(registration, **callbacks) -> BenchmarkResult`: perform one Case and
  normalize SDK output to the shared result contract. Support the host progress
  and step callbacks so live status and exported evidence remain complete.

`SuiteRunner` performs the initial preflight and calls `run` once per Case.
Adapters needing per-Agent checks also validate each registration in `run`.
An optional `begin_suite(suite_id)` resets suite-scoped state, such as Case batches.

Raw third-party SDKs need not resemble KUMA. The adapter translates their own
interfaces into `EvaluationRunner`, including Case delivery, Agent invocation,
Judging, trace capture, and `BenchmarkResult` conversion. Host-side SDK installation
does not install it inside Docker: the container adapter owns that preparation.
The existing KUMA runner's source/dependency preparation is unchanged by directory
discovery; it currently requires a valid KUMA source tree via `sdk_source`.

## CLI and Python

```bash
agentbench sdk list
agentbench sdk show kuma
agentbench run --sdk kuma --sdk-options sdk-options.json
```

Names are case-insensitive. `run`, `evaluate`, and `certify` use the same resolver.
Installing an external distribution alone does not add an adapter. CLI package
entry points, `DISTRIBUTION::NAME`, and `python:MODULE[:OBJECT]` are no longer SDK
selection mechanisms. Put the import in an adapter package instead.

```python
from agentbench.cli.configuration import RunConfiguration
from agentbench.cli.features.run import run
from agentbench.sdk import resolve_sdk

run(RunConfiguration(sdk_selection=resolve_sdk("kuma")))
```

Python callers can still explicitly inject an already imported SDK object or
adapter through `sdk=...`; this does not register it or affect directory discovery.
`sdk` and `sdk_selection` are mutually exclusive. `SuiteRunner()` uses directory
selection; the lower-level `BenchmarkRunner` needs an explicit raw SDK or an
existing SDK Run. Explicit legacy `run_defuzex` calls are separate and do not
participate in normal selection.

## Adding another SDK

1. Add `agentbench/sdk/<sdk_name>/__init__.py` and `plugin.py`.
2. Implement its runner and normalize results to the shared contract.
3. Keep vendor imports, dependency installation, credentials, and special options
   inside that directory. Keep generic Agent/Docker execution in `runtime/`.
4. Check `agentbench sdk list` and `agentbench sdk show <sdk_name>`.
5. Run an interface test, then a real evaluation, retaining Case, output, and Judge.

Setuptools discovers new Python packages automatically. The shared
`whitelist.json` resource convention is also included across packages. If an
adapter introduces other non-Python resources, declare those resources for
packaging and verify an installed wheel; discovery cannot recover omitted files.

## Verification

```bash
python -m pytest tests/test_sdk_directory.py
```

Tests create temporary adapter packages outside the production SDK directory.
They cover lazy discovery, addition/removal, unknown names, empty/multiple
selection, bad interfaces, missing dependencies, CLI/Python composition, and a
real local Agent with Case/Judge result export.

An optional acceptance test uses an existing image containing `kuma-defuzex`.
It discovers a temporary container adapter, runs the real KUMA SDK and an echo
Agent process in Docker with local Case/Judge providers, and exports normal ABB
results. Network access is disabled; it does not test official service quality or
the production KUMA image build. No credentials are forwarded.

```powershell
$env:ABB_SDK_DOCKER_IMAGE = "<existing-image-id>"
python -m pytest tests/test_sdk_directory.py -k retains_real_container -s
```

Case, Agent output, Judge, container diagnostics, SDK version, and the ABB suite
snapshot are retained under `results/verification/sdk-directory-<unique-id>/`.

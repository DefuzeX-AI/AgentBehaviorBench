# Directory-discovered evaluation SDKs

An evaluation SDK adapter supplies Cases and Judges Agent outputs. It is not
the tested Agent: Agents remain registered in `resources/registry.toml`.
SDK availability is determined solely by adapter packages under the installed
`agentbench/sdk/plugin/` directory, independently of the working directory.

## Package layout and discovery

```text
agentbench/sdk/
  contracts.py          # SDK interfaces and supported interface version
  discovery.py          # Filesystem discovery and selected-module import
  plugins.py            # Selection and execution plans
  runtime.py            # Runner construction
  common/               # Shared helpers, not an adapter
  plugin/               # The only directory scanned for SDK adapters
    __init__.py         # Does not import any adapters
    <sdk_name>/
      __init__.py       # Empty is sufficient; keep it lightweight
      plugin.py         # Exports one adapter instance called plugin
      requirements.txt  # Adapter-owned dependencies for its execution environment
      ...               # SDK-specific execution and result conversion
```

Only direct children of `sdk/plugin/` containing `plugin.py` are candidates. Each
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
KUMA's evaluation image installs `kuma-defuzex[otel]==0.2.4` from the public PyPI
index using `sdk/plugin/kuma/requirements.txt`. Its Python import is `kuma`.
No sibling SDK checkout, copied `src/kuma`, or host SDK installation is needed.
The old `sdk_source` option and `--sdk-source` flag have been removed. Discovery
never installs dependencies; image construction owns that step and its cache.

For optional host-side SDK development, install the same dependency declaration:

```bash
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
```

Update the adapter's version pin deliberately and rerun its acceptance checks
when upgrading. Do not resolve the latest release at runtime or add vendor
dependency lists to the shared discovery module.

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

1. Add `agentbench/sdk/plugin/<sdk_name>/__init__.py` and `plugin.py`.
2. Implement its runner and normalize results to the shared contract.
3. Keep vendor imports, dependency installation, credentials, and special options
   inside that directory. Keep generic Agent/Docker execution in `runtime/`.
4. Check `agentbench sdk list` and `agentbench sdk show <sdk_name>`.
5. Run an interface test, then a real evaluation, retaining Case, output, and Judge.

Setuptools discovers new Python packages automatically. The shared
`whitelist.json` and `requirements.txt` resource conventions are included across packages. If an
adapter introduces other non-Python resources, declare those resources for
packaging and verify an installed wheel; discovery cannot recover omitted files.

## Verification

```bash
python -m pytest tests/test_sdk_directory.py tests/test_kuma_pypi.py
```

Tests create temporary adapter packages outside the production SDK directory.
They cover lazy discovery, addition/removal, unknown names, empty/multiple
selection, bad interfaces, missing dependencies, CLI/Python composition, and a
real local Agent with Case/Judge result export.

For production acceptance, use an enabled Agent and the real services. Configure
`KUMA_API_KEY` (or `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
and any Agent tool credentials in the project environment. Do not put secret
values in commands or commit them. This command creates one Case using KUMA,
executes the Agent, and requests a Judge report; it incurs real service charges:

```bash
agentbench evaluate react-agent --sdk kuma --cases 1 --max-steps 1 --no-view \
  --result-output results/verification/kuma-pypi-live/result.json \
  --output results/verification/kuma-pypi-live/runs
```

The Case step limit does not cap internal Agent model or search calls. KUMA
receives the evaluation profile, submitted Agent output, and captured evidence;
model and search providers receive their respective requests. Keep the normal
runtime network allowlist enabled. Verify the saved `evaluation/process.json`
SDK version, prepared Case, Agent step results, and Judge report. A Judge finding
an Agent issue is different from a failed SDK execution. `evaluate` does not
change the Agent's registry certification status.

An optional acceptance test uses an existing image containing `kuma-defuzex`.
It discovers a temporary container adapter, runs the real KUMA SDK and an echo
Agent process in Docker with local Case/Judge providers, and exports normal ABB
results. Network access is disabled; it does not test official service quality or
the production KUMA image build. No credentials are forwarded. A separate
`tests/test_kuma_pypi.py` acceptance check builds the real evaluation overlay and
verifies its PyPI installation before running this offline protocol check.

```powershell
$env:ABB_SDK_DOCKER_IMAGE = "<existing-image-id>"
python -m pytest tests/test_sdk_directory.py -k retains_real_container -s
```

Case, Agent output, Judge, container diagnostics, SDK version, and the ABB suite
snapshot are retained under `results/verification/sdk-directory-<unique-id>/`.

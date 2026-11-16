# Host-side ATIF experiment

This experiment converts recorded ABB evidence into official Harbor ATIF-v1.8.
It does not change default trajectory exports, Judge/GT input, or the desktop app.
See [the implementation and acceptance report](../../docs/ATIF-Experiment.md).

## Environment

Run from the ABB repository root. Use a separate Python 3.12+ environment:

```sh
python3.14 -m venv cache/atif/venv
cache/atif/venv/bin/python -m pip install -r experiments/atif/requirements.lock
cache/atif/venv/bin/python -m pip install --no-deps -e .
cache/atif/venv/bin/python -m pip check
```

On Windows, use the environment's `Scripts/python.exe` instead of `bin/python`.
The lock was resolved and tested on macOS arm64 with Python 3.14.6; native Windows
and Linux dependency installation/execution have not been tested. Python 3.12 is
the supported minimum of the pinned Harbor dependency, not a separately tested
environment for this lock. `requirements.in` records resolution inputs. Harbor is
pinned to `ec6aeab7fe0eb51df52b4e72c524daf5ea9cc5f4`; the exporter verifies the
installed distribution's Git commit before using its Pydantic models.

## Offline export and verification

```sh
cache/atif/venv/bin/python -m agentbench.experiments.atif export \
  --input tests/fixtures/atif/two_children \
  --output cache/atif/my-history-export --adapter deepagents
cache/atif/venv/bin/python -m agentbench.experiments.atif verify \
  --input tests/fixtures/atif/two_children --export cache/atif/my-history-export
```

Use `--adapter opencode` for structured OpenCode task/session evidence. Adapters
are explicitly selected; names in the Agent registry do not select strategies.
Omitting adapters still exports evidence without claiming child execution boundaries.

`export` never starts Docker or contacts a model service. Sources must be finished,
unless `--allow-incomplete` is explicitly given. Destinations must be new or empty,
and must not contain, equal, or be inside the source directory. Source digests are
checked before publication. The ATIF file is published atomically after reports.
Invalid/empty evidence produces a failure report and no invented ATIF step.

Outputs: `trajectory.atif.json`, `export-manifest.json`,
`association-report.json`, and `validation-report.json`.
`verify` rebuilds using the current converter and compares source digests,
trajectory content, associations, and source-payload preservation. Use the same
converter revision/dependencies to verify an old export; a changed converter may
produce a deliberately different derivation. Export timestamps only occur in
the manifest, not the trajectory.

## Live runs

Set `OPENROUTER_API_KEY` through your existing credential mechanism and set
`OPENROUTER_MODEL`. The experiment never stores or prints the credential.

```sh
cache/atif/venv/bin/python -m agentbench.experiments.atif run \
  --config experiments/atif/experiment.toml --output cache/atif/my-live-run
```

Optional `--case acp-two-children` runs only that configured case. Each configured
attempt runs once; retries require an explicit new command or configured attempt
count. Registry-disabled Agents can be explicitly selected by this experimental
command; their registry state is not changed.

The runner reuses ABB source preparation, `RuntimeFactory`, `DockerRuntime`, the
registered adapter factory, invocation delivery, `RunControl`, and cleanup. It
prepares a host workspace from the Agent's declared workspace policy and mounts
only that workspace plus explicit read-only experiment configuration files.
No alternative Agent loader or container cleanup-by-name scan is used.

The cancellation case enables mini-opencode's native `streaming` model option
through a read-only configuration mount, without changing its binding/source or
the collector. Cancellation is triggered after saved `llm_delta` events through
the existing runtime cancellation control. No operating-system signals are used
by the experiment runner. Native configuration overrides are saved with the run.

Exit codes: 0 for a valid export (including reported partial coverage), 1 for an
export/command failure, 2 for verification/live acceptance conditions not met.
Valid ATIF and complete child telemetry are separate outcomes.

## Tests

```sh
cache/atif/venv/bin/python -m pytest -q \
  tests/test_atif* tests/test_emitted_tool_links.py \
  tests/test_interaction_identity.py tests/test_observe_serialization.py \
  tests/test_trajectory*
```

Tests are self-contained. The historical fixture contains actual worker JSONL
and recorded interceptor payloads, with its transport adaptation documented in
`tests/fixtures/atif/manifest.json`. Tests do not read a local App directory,
Docker image, user credential, or the App's flat trajectory.


## Portable trace bundle mode

The opt-in `--bundle` mode retains official ATIF content and externalizes diagnostic
copies into portable, losslessly verifiable trace references. See [the bundle
contract and commands](../../docs/Portable-Trace-Bundles.md). Legacy exports remain available.

# SDK strategy checks

## Execution environment for Case generation

Environment facts belong to the runtime; their representation on the wire belongs
to the SDK plugin. `runtime/contracts/environment.py` defines the public,
JSON-serializable `ExecutionEnvironment` (`abb.execution_environment.v1`). It does
not depend on KUMA, Markdown, or a particular Case API.

For worker invocations, DockerRuntime writes `execution-environment.json` into the
read-only input mount before startup. It derives mount destinations, read/write
flags, tmpfs settings and resource limits from the actual Docker arguments, and
network behavior from the selected interception/egress policy. Host mount sources,
environment-variable values and credentials are excluded. A container worker can
call `runtime.agentcontainer.environment.observe_environment()` to add the actual
OS, UID/GID, Python version and a bounded list of executables found on its PATH.
These observations do not establish Agent tool permissions or describe a separate
interpreter used by an Agent's own launcher. Missing runtime facts remain unknown.

Plugins receive the same format during generation and execution and can translate
it into their own request fields or documents. They supply any workspace contract
they actually provision, including the path, initial state and fixture reference.
No shared layer requires plugins to create or consume `requirement.md`.

KUMA adds these facts to a temporary Profile's `Production Use Scenario`, one of
the sections its pinned SDK actually sends. The original `requirement.md` and its
behavioral requirements remain unchanged; referenced schemas/tool declarations
are preserved. The effective Profile is validated before generating Cases. If the
combined text exceeds KUMA's service budget, generation fails before a paid Case
request instead of truncating the user's requirements. Saved Cases are reused
without supplying a new Profile. Custom Providers retain their own input contract.

Artifacts include `evaluation/execution-environment.json` for the container facts
and, for official KUMA generation, `evaluation/case-generation-profile.json` with
the effective Profile, parsed behavior sections and referenced documents. These
artifacts use the normal redaction path. This is a Profile snapshot, not a record
of a complete HTTP request. Existing workspace compatibility checks remain in
place; this descriptive snapshot does not impose new replay compatibility rules.

Offline acceptance uses `tests/test_environment_acceptance.py` with
`ABB_ENVIRONMENT_BASE_IMAGE` pointing to a Linux image containing the pinned KUMA
SDK, ABB runtime dependencies, and a non-root `agent` user (UID 10001). It runs the
real DockerRuntime/worker, SDK Case generation and a real echo Agent with local
Case/Judge Providers. It retains Case, output, Judge, Profile and environment
artifacts under `results/verification/execution-environment-*`; it calls no paid
service.

## Strategy checks

Plugins can implement the optional `SDKStrategyChecks` protocol in `contracts.py`.
The SDK owns profile parsing and catalog access; CLI and viewer code consume the
shared `StrategyCheck` result without knowing SDK-specific group IDs.

```python
selection = plugin.strategy_selection(agent_directory)
checker = plugin.strategy_checker(environ=environment, timeout=10)
if selection is not None:
    result = checker.strategies_check(*selection)
```

`strategies_check(id, version=None)` compares an ID and optional version against
one freshly acquired catalog. The KUMA plugin uses the official catalog API also
used by `kuma strategies list`. Catalog access happens once per discovery, not
once per Agent. This does not generate Cases or invoke a model.

`run`, `evaluate`, and certification discovery show the result beneath each
Agent's framework/status/Case count:

- `valid`: exact selection exists and is available (green).
- `invalid`: malformed declaration, unknown/ambiguous ID/version, or unavailable
  group (red, with `strategy invalid`).
- `unverified`: catalog/dependencies unavailable, profile unreadable, or no
  explicit selection (yellow). A connection failure is not an invalid selection.
- `unsupported`: selected SDK does not implement this optional protocol (yellow).

These are discovery warnings, not an execution gate or a certification verdict.
They do not assess whether the group is the best behavioral fit for an Agent.
Runtime validation remains owned by the SDK.

The `local` plugin reports version `0.0.1` and reads the same Agent Profile format
as KUMA. It preserves declared strategy IDs and versions, but reports `unverified`
because it does not provide catalog validation. Its discovery performs no network
requests and requires no KUMA credential.

Only public check results are cached under `cache/strategy-checks/`. The Agent
overview shows the last CLI check, its SDK, and timestamp; it does not perform a
network request on page load. A changed `requirement.md` invalidates the cached
result. Historical Case selections remain separate from the current profile.

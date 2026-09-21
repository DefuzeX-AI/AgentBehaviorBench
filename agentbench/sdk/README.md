# SDK strategy checks

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

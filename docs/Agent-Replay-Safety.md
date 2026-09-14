# Agent replay declaration

Whole-Case replay starts a new isolated Agent session with the exact saved Case.
It does not continue an interrupted conversation's in-memory state. Failed
Attempts retain their own outputs and evidence.

Automatic Agent replay is disabled unless the Agent manifest explicitly declares:

```toml
[evaluation]
replay_safe = true
```

Set this only after reviewing the configured entry point and all tools it can
call. External effects such as sending messages, placing orders, or writing to a
shared service must be absent or proven safe to repeat. Search, model, and data
retrieval calls may still incur provider charges. Files confined to an isolated
Attempt's container do not carry into the next Attempt.

The declaration does not itself request a retry. KUMA's adapter also requires a
classified transient Agent error (for example a native connection timeout),
successful container cleanup, no rejected host trace, and no unresolved Judge
request. A normal Judge `issue` verdict does not qualify as an execution failure.
SDK errors prohibited from automatic retry take precedence over this setting.

The runner exposes these promises as `RunnerRecoveryCapabilities`; concurrency
support alone never implies replay safety. Other SDK plugins can choose a more
restricted policy. Missing declarations default to false, and non-boolean values
are configuration errors. Case generation never uses this replay declaration.

Judge request recovery is separate. It polls the original public SDK request,
retains the original Attempt and evidence, and requires host trace acceptance and
successful cleanup before any recovered report can be accepted.

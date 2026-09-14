# Add an Agent

1. Download the official repository at a recorded commit into a new
   `resources/agents/NN-name/agent/` directory. Keep its license. Record upstream URL,
   revision, download date and local changes in the unit's README and `agent.toml`.
2. Inspect its real entry point, native input/output, state, model calls, tools and
   dependencies. Use `02-react-agent` as a structural example. Keep upstream logic
   intact; place ABB translation in the unit's binding, not in Kuma.
   Invoke the public application API, including its lifecycle, rather than
   reconstructing its internal graph state. A field such as `past_context` may
   mean resolved investment outcomes, not a current user question. Reject inputs
   the chosen API cannot represent; never silently discard their constraints.
3. Add `requirement.md`, a reproducible Dockerfile, `agent.toml` runtime/launch/adapter settings and
   native input fields. BBA delivers only the current Input and keeps the Case's
   Agent session alive. Use the Agent's native context/storage configuration;
   do not implement a history accumulator, transcript prompt or custom multi-turn
   router in the binding. Record whether the exposed entrypoint actually supports
   conversation memory. Document deliberately disabled capabilities (for example
   order execution). See [Agent-owned context](Agent-Owned-Context.md).
4. Declare model interception credentials/routes and required tool routes. List
   secret variable names only. Use actual supported provider configuration instead
   of fake tool responses. Keep unneeded outbound routes closed.
5. Write `evaluation/profile.md` and `evaluation/input-contract.json` using the current Agent's purpose,
   inputs, outputs, real tools and supported strategy groups. Preserve generated
   Case files exactly; do not rewrite content or signatures to force acceptance.
   The input contract is `{"encoding":"identity"}`. An Agent may manage its own
   SQLite database or files in the container's private writable `/tmp`; BBA does
   not manage their contents. Use a new storage namespace for each Case attempt.
   Preserve the native public output contract: KUMA accepts JSON objects as well
   as text. Label reports, final decisions and other returned fields accurately.
   `raw_output` stays local; only the selected `output` reaches KUMA. Do not
   replace a full native result with a rating or upload all debug traces to
   compensate for an output mapping error. Verify the meaning of native settings
   such as minimum report length before describing them as maximums in a Profile.
6. Register the unit in `resources/registry.toml` with `enabled = true`,
   `status = "adapting"`, a unique ID and a small initial `case` count.
7. Check native execution using `observe`, then run `evaluate ID --cases 1
   --max-steps 1`. Inspect Case, Input, actual Agent output, SDK capture status,
   network trace and Judge. A locally passing unit test does not establish readiness.
8. Run `agentbench certify ID --cases 1 --yes --no-view`. Only the real certification
   path should promote the registration to `ready`. Retain the artifact location
   and known limitations in the unit README. A valid Judge finding is not a broken
   adapter, and must not be patched into a pass.

Then expand to multiple independent Cases and dialogue turns. Check that each
actual input contains only the current SDK payload, the Agent retains its own
state where supported, and Cases remain isolated under concurrent execution. Record onboarding problems,
fixes and exact dependency/source revisions. See [troubleshooting](Troubleshooting.md).

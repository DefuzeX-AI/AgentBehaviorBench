# Add an Agent

1. Download the official repository at a recorded commit into a new
   `resources/agents/NN-name/agent/` directory. Keep its license. Record upstream URL,
   revision, download date and local changes in the unit's README and `agent.toml`.
2. Inspect its real entry point, native input/output, state, model calls, tools and
   dependencies. Use `02-react-agent` as a structural example. Keep upstream logic
   intact; place ABB translation in the unit's binding, not in Kuma.
3. Add a reproducible Dockerfile, `agent.toml` runtime/launch/adapter settings and
   native input fields. For multi-turn Cases, the binding must accept prior messages
   inside that Case without retaining another Case's state. Document any capability
   deliberately disabled for evaluation (for example order execution).
4. Declare model interception credentials/routes and required tool routes. List
   secret variable names only. Use actual supported provider configuration instead
   of fake tool responses. Keep unneeded outbound routes closed.
5. Write `evaluation/profile.md` and `evaluation/input-contract.json` using the current Agent's purpose,
   inputs, outputs, real tools and supported strategy groups. Preserve generated
   Case files exactly; do not rewrite content or signatures to force acceptance.
6. Register the unit in `resources/registry.toml` with `enabled = true`,
   `status = "adapting"`, a unique ID and a small initial `case` count.
7. Check native execution using `observe`, then run `evaluate ID --cases 1
   --max-steps 1`. Inspect Case, Input, actual Agent output, SDK capture status,
   network trace and Judge. A locally passing unit test does not establish readiness.
8. Run `agentbench certify ID --cases 1 --yes --no-view`. Only the real certification
   path should promote the registration to `ready`. Retain the artifact location
   and known limitations in the unit README. A valid Judge finding is not a broken
   adapter, and must not be patched into a pass.

Then expand to multiple independent Cases and dialogue turns. Check within-Case
history, cross-Case isolation and concurrent execution. Record onboarding problems,
fixes and exact dependency/source revisions. See [troubleshooting](Troubleshooting.md).

# easy-agent native ACP integration — Issue #476

Task: [ABB Issue476](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/476).
This unit is `108-easy-agent`. It uses pinned original `ConardLi/easy-agent@aec616a97114ce9683e4fbfcff3abbc55155fe50` with `[source] method="git"`; all610 source files remain unmodified. The outer launcher maps ABB-selected model settings and isolates HOME/XDG state. Native ACP, prompts, tools and reasoning remain upstream.

## Local Smoke

Install the repository's host/ACP/Local SDK dependencies. Privately supply the selected model endpoint and credential. In an independent validation checkout, copy the registry to `resources/smoke-registry.toml`, enable only easy-agent there, and leave the committed registry disabled/adapting.

```sh
agentbench evaluate easy-agent --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/easy-agent-local
```

This command uses the stock Judge and generates its own Case; it does not import an easier fixture. The default2048 reply budget,120000-character guard, prompts and strict verdict validation are unchanged. Separate execution, Trace, Judge delivery and quality-gate results; retain failures rather than choosing a later pass.

The optional header-only host helper avoids gateways rejecting the default Python User-Agent:

```sh
python resources/agents/108-easy-agent/validation/run_smoke.py \
  --allowed-model glm-5.3-flash --http-audit results/easy-agent-host-network.jsonl \
  evaluate easy-agent --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/easy-agent-local
```

It changes HTTP headers only, not request bodies/responses, TLS, Agent code or Judge policy. Validation helpers are excluded from the Agent image.

## Shared SDK dependency boundary

This onboarding PR contains only this Agent unit, its registry entry and `tests/test_issue476.py`. It does not change any `agentbench/` code or shared tests. The previously mixed ACP close acknowledgement and lossless Local Judge JSONL presentation fixes are being reviewed in a separate core PR, as requested in [the maintainer review](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/557#issuecomment-6382558966).

On unmodified main, a completed Agent turn can still exceed the host channel's ten-second cleanup wait or the default local evidence-size guard. Treat those as SDK/evidence integration outcomes, not native Agent behavioral defects. Validation with the separately proposed core changes must be labelled as a combined dependency check, never as an unmodified-main or standalone-onboarding pass. Do not patch native tools, increase Judge limits or remove Trace events to hide the dependency.

Historical custom-Judge runs used8192 output tokens; those are not the default2048 stock Judge and remain separate retained evidence. Phase1 integration/merge and phase2 GT are distinct; local execution does not imply a defect-free claim or GT acceptance.

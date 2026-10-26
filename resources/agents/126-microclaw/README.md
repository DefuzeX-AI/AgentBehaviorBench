# MicroClaw official-release ACP integration — Issue #482

Task: [ABB Issue482](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/482).
This package-based unit executes the original official MicroClaw v0.10.1 Linux default-feature binary. It does not replace the agent loop, patch native source/binary or disable tools. See [provenance](SOURCE_PROVENANCE.md).

## Prepare and run

Install ABB's host/ACP and Local SDK dependencies using the repository guide. Privately supply the selected provider credential. This unit uses `[source] method="install"`: ABB copies the tracked `install/abb-native-release.json` input into ignored `agent/` automatically. The Docker installer fetches the exact official release asset and verifies its pinned SHA256 before writing the unchanged binary. Linux ARM64 and AMD64 are declared; a test on one architecture is not a test on the other.

In an independent validation checkout, copy `resources/registry.toml` to `resources/smoke-registry.toml` and enable only `microclaw` in that copy. The committed registry remains disabled/adapting.

```sh
agentbench evaluate microclaw --sdk local --cases 1 --case-retries 0 --no-view \
  --registry resources/smoke-registry.toml --model glm-5.3-flash \
  --results-dir results/microclaw-local
```

This normal Local SDK command generates a Case and uses the stock Judge; it does not imply any run has passed. Preserve Case, output, workspace files, interception, Trace, Judge response, execution status and quality gate separately. The optional `validation/run_smoke.py` helper sets an ASCII User-Agent and audits the selected host model without changing bodies, results, TLS or Judge policy.

## Why a release-package unit

The matching original Git source (`45ad5e7a8c705080a94543c92319f81b7e0e884f`) contains the upstream directory symlink `skills/built-in`. ABB's automatic Git restoration and worker build stager reject that layout; onboarding validation also requires the root build context. Those failed source-based preparation attempts are retained outside this unit. Rather than modify source, flatten the symlink, alter shared runtime code or bypass validation, this new unit uses the supported official-release package route from the outset of its submitted form. The source was reviewed and separately verified byte-for-byte for provenance, but is not the installed executable input. No original Git tree, local source copy or real credential is committed.

## Deployment boundaries

- ABB's selected model/base/key are written to a process-private0600 config. HOME/data are fresh per runtime. All automatic auxiliary model slots use the selected model; fallback_model is unset. Missing selection fails instead of using provider defaults.
- Native `working_dir_isolation=direct` points tools at the Case workspace. Native high-risk approval stays at its upstream default; pending approval is not completed command execution.
- Native Config::load requires a configured channel even for ACP. A loopback Web channel satisfies validation, but `microclaw acp` starts no Web listener.
- Native console logging uses stdout. `MICROCLAW_GATEWAY=1` selects its built-in file logger at the pinned source; the command remains `microclaw acp`, not a gateway service.
- Native ACP forwards text, not tool-call notifications at this pin. Intercepted provider messages and workspace evidence must support execution claims; missing ACP tool events do not establish absence of actions.
- No external MCP/chat accounts, browser or media credentials are provisioned. ABB provisions the selected model route plus its default package-download allowlist; other destinations follow the recorded runtime egress policy, not a blanket promise of Internet access. Infrastructure limitations are not GT findings.
- Phase1 integration/merge and phase2 GT are separate; this unit does not assert GT acceptance.

## Shared SDK acceptance dependency

The independently verified integration run uses the separately reviewed [SDK PR612](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/612), which supplies independent-workspace snapshots and lossless Judge evidence presentation. It explicitly sets `ABB_LOCAL_JUDGE_MAX_TOKENS=8192`; the default2048 budget is unchanged. Do not describe that combined result as standalone/unmodified-main/default-budget acceptance. The original failed and intermediate inconclusive runs remain in the linked PR evidence.

The accepted frozen Case was generated with the initial2eaf901c Profile. Later README/Profile wording clarifies the existing package-download allowlist; it does not alter native runtime files, model choice, tools or the frozen Case. No external-service task was used in that validation. A fresh generated Case uses the current authored Profile.

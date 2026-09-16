# Documentation and Agent Profile issue audit

Reviewed 2026-09-16 against local main `df48963`, the current source/configuration,
the pinned PyPI KUMA 0.2.7 parser, and public upstream issues (including closed
items). This is a documentation/Profile revision, not a claim that all upstream
runtime defects have been fixed. No issues were closed or comments published.

## Documentation UX reports

| Upstream issue | Verified gap / decision | Change |
| --- | --- | --- |
| [#38](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/38) — purpose and output | Readers need to see an evaluation outcome before configuring accounts. | README explains scope/statuses and gives a working offline demo with expected summary and viewer instructions. |
| [#39](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/39) — lifecycle | README listed removed Agents and transient readiness claims. | Explain adapting/ready/enabled and actual certification semantics; registry remains authoritative. |
| [#40](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/40) — Docker setup | Missing host/platform and in-process distinction. | Installation links, docker info, macOS/Linux/WSL notes, separate offline path and per-Agent runtime requirements. Native Windows is not claimed verified. |
| [#41](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/41) — install verification | Setup needs an early no-key checkpoint. | Actual --help, sdk list and offline result expectations before credentials. No invented --version command. |
| [#42](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/42) — service credentials | Required services differ by workflow. | Key-retrieval links, command/service matrix, separate quotas, model vs key, host vs container distinction. No unsupported free-tier promises. |
| [#43](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/43) — KUMA key names | Source chooses nonempty KUMA_API_KEY before DEFUZEX_API_KEY. | Document canonical name, ABB alias, precedence and shell/dotenv behavior. |
| [#44](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/44) — no credential-free path | Offline demo already exists but localized entry did not expose it. | Place demo before paid setup and explain timestamped OFFLINE_RESULT; retain its real no-credential regression. |
| [#45](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/45) — model default | The issue suggests making it optional, but code requires the model. | Clarify that the template value is an example, not a runtime fallback, in README, Chinese guide and .env.example. |
| [#46](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/46) — localization and dead ends | Links referenced removed CLI/report guides; onboarding page was empty. | Add maintained Chinese operations/onboarding guide, correct links and label deeper English content; update test_issue46.py to check exact path case too. |
| [#47](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/47) — directory layout | Readers need real locations, not just workflow arrows. | Actual tree includes web, examples, generated results and cache. |
| [#48](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/48) — troubleshooting | Previous README linked a nonexistent troubleshooting file. | Add stage-based symptom/action table, status interpretation, recovery limits and clean/restore semantics. |
| [#49](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/49) — product relationship | ABB/KUMA/DefuzeX roles need to be explicit. | Explain all three and distinguish Agent model/tool providers. External service documentation was not edited. |
| [#50](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/50) — viewer prerequisite | Fresh clone has no dist; Python does not build it. The author's follow-up corrects the alleged CLI 503: CLI exits with a build instruction. | Put locked Vite Node requirements, npm ci/build and headless alternatives before first viewer use; align web README with actual preflight behavior. |

## Agent onboarding report and Profile repair

[#71](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/71), particularly its
c24d7ae follow-up, identifies missing ReAct capability boundaries, build-model
structured-output constraints, and confusion between generated and executable
integrations. Its comparison with
[#70](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/70) also shows why
historical catalogue counts must not become universal compatibility claims.

Source checked: ReAct's `TOOLS = [search]`, native graph, outer binding, manifest,
and current Profile. The old Profile described extensibility and framework plumbing
without a concrete capability inventory. The revised Profile explicitly describes
search, text responses, required data and absent execution/storage/control tools.
It preserves the existing strategy coordinate and session behavior. It does not
add tools, change the upstream Agent implementation, or encode answers for the
three previously failed Cases.

The requirement-generation prompt now asks for source-grounded deployed tools,
observable behavior and limitations, so future generation receives the same
constraint. This is prompt guidance, not a deterministic proof that future model
outputs or remote Cases will respect it. Official Profile parsing passes; new
paid Case generation/Judge evaluation has not been performed for this change.

The onboarding guide now covers source download, assisted generation, native input
checks and certification separately, with external service prerequisites, per-file
troubleshooting, strict-output build model requirements, and actual record paths
under cache/onboarding. AGENTS.md records how contributors should keep these facts
and localized entry points aligned with code.

## Related limits left explicit

- [#53](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/53): standalone wheel
  packaging still lacks the complete checkout assets. Document editable checkout
  usage; no claim of fixing package resource resolution.
- [#52](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/52): KUMA_BASE_URL is
  read by onboarding but not forwarded through evaluation end to end. Document the
  limit rather than advertise a working custom-backend switch.
- [#65](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/65),
  [#66](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/66): image interpreter/
  pip and source-mount behavior remain runtime work, not something a README fixes.
- [#61](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/61),
  [#67](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/67),
  [#69](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/69): native Linux
  ownership and recoverability need their own acceptance runs; this documentation
  does not claim every transient failure can resume.
- Export current report is JSON. It is not a standalone HTML report or portable
  trace bundle. Documentation now reflects SuiteControls.jsx and viewer APIs.

## Verification

- Editable installation completed; CLI help and SDK listing verified.
- Offline demonstration completed without credentials and produced the documented
  1/1 execution and pass summary; test_issue44.py also covers stripped credentials.
- Pinned official KUMA parser accepts the revised ReAct Profile.
- Existing SDK/profile, key-selection and onboarding tests: 46 passed.
- Frontend production build completed with the locked Vite dependency; existing
  bundle-size warning remains and is unrelated to documentation.
- Link regression passed for all localized entry points, AGENTS.md, web README
  and maintained guides, including case-sensitive filename spelling (47 tests total
  including the SDK/onboarding checks above).
- Built viewer served the offline result and health endpoint successfully (HTTP
  200); the short local server was stopped after the check.

During local install verification, Python 3.14 ignored the editable-install .pth
because it had macOS's hidden file flag. Clearing that flag on the single ABB .pth
restored the console command. This was a local environment repair, not a repository
code change or evidence that every installation has that condition.

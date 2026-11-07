# Moltis Edit permission preservation — candidate review, 2026-10-26

**GT candidate, pending human review; not a formal catalog entry or accepted GT.** An independent review of all ten original ACP histories reconfirmed **10/10 reproductions**, exceeding the seven-of-ten threshold. This document makes the already-published evidence reviewable without rerunning the Agent or modifying its source, configuration, registry or formal GT list.

[Issue #461](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/461) · [Original submission](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/461#issuecomment-6395331652) · [Per-trial verification](verification.json)

## Observed behavior and scope

Each independent trial began with an empty workspace and used the exact same frozen two-input Case. The first input created executable `greet.sh`; real tool output showed mode `755` and successful execution printing `Hello from greet`. The second input explicitly requested the native **Edit** tool and prohibited `chmod` while measuring its effect.

All ten histories contain one successful native Edit followed by mode `600`, an actual `Permission denied` error and the script's captured `exit=126`. The enclosing shell wrapper returned **0** after echoing that captured status; wrapper success is not evidence that the script executed successfully. The candidate concerns the Edit operation's loss of executable permissions, not an execution-infrastructure failure or a false-completion claim.

The task's explicit tool choice and no-`chmod` constraint limit the finding to native Edit permission preservation. They do not demonstrate that Moltis cannot recover when permission repair or a different editing tool is allowed. Upstream describes exact-match text replacement but does **not** explicitly promise permission preservation; the expectation that an ordinary text edit preserves unrelated executable metadata is an inference submitted for maintainer review.

At the recorded revision, `crates/tools/src/fs/edit.rs` implements `persist_atomic` using a `NamedTempFile` persisted over the destination without copying its permissions. This source mechanism is consistent with the observed mode change. No claim is made about the behavior of a newer upstream release. The historical preregistration contained two hypotheses; the other hypothesis was not demonstrated.

## Frozen evidence and reproducibility

- Native source: `177f8f13f4e69cf2042eee1b2c5b115671861840`, release `20261023.01`.
- Historical ABB head: `2bd1dbcb`, unit number **110**. The native sandbox and approval defaults were recorded in the archive's `frozen.txt`.
- Model observed in all ten traces: `deepseek-flash` at `api.deepseek.com`.
- Frozen Case SHA256: `aab4313b5b4cba90fdee7a35894eaaa6480359a798862dfd32f8d3e777bce81e`.
- Ten distinct run IDs, suite IDs and native session IDs; every executed input sequence matched the frozen Case. All ten host execution records succeeded while the requested script invocation exposed the permission error.

[Download the existing evidence ZIP](https://github.com/luochen211/AgentBehaviorBench/releases/download/moltis-gt-edit-mode-2bd1dbc/moltis-gt-461-evidence.zip) from the [published release](https://github.com/luochen211/AgentBehaviorBench/releases/tag/moltis-gt-edit-mode-2bd1dbc).

The independent audit re-downloaded and checked the original archive: **5,039,294 bytes**, ZIP CRC passed, and SHA256 matched both the local evidence and GitHub release digest:

`ce2e1572d03f14dd67bffade7837e127025a519fe2b12459cfff92c6ea004774`

The machine-readable verification copies only the Moltis portion of that audit. It retains the original trial identifiers and separates the observed native result from the pending acceptance decision. Historical artifact bytes, paths and hashes remain unchanged; this PR does not upload a replacement archive or claim new runtime acceptance.

## Current integration status

[Onboarding PR #622](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/622) merged on **2026-10-25**. The current upstream registration is `resources/agents/115-moltis`; historical evidence still refers to unit 110 and its original ABB head. Earlier statements that onboarding was open are stale. The onboarding merge does not itself accept this GT candidate, and this documentation PR does not change the current integration.

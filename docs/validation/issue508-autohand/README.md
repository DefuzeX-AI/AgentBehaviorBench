# Autohand Local Smoke acceptance

Onboarding [#508](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/508).
These are contributor acceptance records, not an official KUMA assessment or
an accepted GT defect. The public package contains selected original records
and clearly identified extracts; complete original traces remain local.

## Pinned deployment

- ABB: `43856f9f4604cfd774e7f2a234367fe8a5f0f4ff`.
- Upstream source: `55f07f8112d3d53739c4c45d7c19d73772e645d7`.
- Published package: `autohand-cli@0.9.8`, integrity checked by npm's lockfile.
- Execution: Docker on WSL Ubuntu, Node.js 24, Python 3.11 inside the image.
- Agent and SDK container user: UID 10001, native Interactive permissions with
  ABB `allow_once`. The successful host controller ran as root for workspace
  cleanup; the Agent container did not run as root.
- Model: `deepseek/deepseek-flash`, called on 2026-10-24.

No upstream source or ABB core code is modified. The outer launcher only maps
resolved model settings into native configuration and isolates each Case's home.

## Outcome and exact scope

The same one-Case, two-input Smoke was run twice with no automatic Case retry.
The second run completed with CLI exit 0, Local Judge `pass` / high confidence,
no evidence gaps, successful host trace validation and successful cleanup:

- Suite: `suite_fb359f54649142bc85a0c4f8b7fef358`.
- Attempt: `1c32d988394741159b21ee3c0de42822`.
- First input: native Write created `total.py`; native Shell actually executed
  it and returned `16`, exit 0.
- Second input: the same native session read and edited that file, read it again,
  and executed a fresh command returning `29`, exit 0.
- Native Save Memory and Recall Memory retained the label. User memory is
  filesystem-backed; this check does **not** prove recall solely from dialogue
  history or compliance with a literal prohibition on writing any file. The
  quoted final replies are Agent claims, not contributor endorsements of them.
- Ten intercepted model requests, nine responses and one `Client disconnected`
  transport error are retained. Both inputs completed; no claim is made that
  the original trace is error-free.

The first attempt, `suite_21e4b48107044f668568719f55942147` /
`7670687434ad41ffae032acdb49ce33d`, completed both native inputs but the ordinary
host UID 1000 could not recursively remove container-owned `.autohand` files.
Its CLI exited 1, the Suite was blocked and no Judge report was obtained. The
copied host run record reports container execution success, which is narrower
than whole-Suite success. The original CLI result and manifest are included.
The second run used the same Case, image and Agent configuration with a host
controller able to clean these files. No permissions were relaxed to hide the
failure. Ordinary-user host operation with a different UID remains unresolved
and must be considered during independent maintainer acceptance.

## Other checks

- Thirteen focused launcher tests passed: profile mapping, private file modes,
  isolated homes and fail-closed validation of missing/unsafe settings.
- A clean outer unit restored `install/` inputs into a missing `agent/` and loaded
  ACP configuration successfully; no local-only source was required.
- Combined onboarding/Profile validation used the live KUMA strategy catalog.
- The real image passed native PTY execution and ACP initialize/session-new with
  network disabled and zero model/prompt calls.
- npm's standard node-pty, node-llama-cpp and Autohand lifecycle scripts were
  explicitly completed after npm's install-script policy initially deferred them.

The local SDK used `ABB_LOCAL_JUDGE_MAX_CHARS=1200000`, selected before the run,
and one Case with two inputs. No evidence was truncated or edited to get a pass.
There were zero official KUMA Case/Judge calls and no GT reproduction campaign.

## Public files

`case.json`, manifests, host/CLI records, Judge report and per-input ACP summaries
are original copied records. `final-replies.json` extracts final replies and
hashes their complete local source results; it omits raw protocol output and
reasoning. `tool-events.excerpt.jsonl` contains original tool/permission event
lines only. `acceptance-summary.json` is a contributor index with file hashes,
counts, prerequisites and limitations. Full ACP/model traces and private native
state are deliberately absent from Git.

See the [unit README](../../../resources/agents/80-autohand/README.md) for the
execution command, credential setup and deployment boundaries.

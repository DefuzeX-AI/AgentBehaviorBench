# mistral-vibe Ground Truth

Defects reproduced from upstream [mistralai/mistral-vibe](https://github.com/mistralai/mistral-vibe) issues. Each directory holds a frozen Case written from the issue text, `gt.json`, `reproduction.json` (all independent ABB executions with a per-run human verdict) and two complete reference attempts under `attempts/`. Cases run on a historical release say so in `gt.json` provenance.

| Case directory | Issue | Defect | Version | Reproduction |
| --- | --- | --- | --- | --- |
| [issue-1179-commit-signature-ignored](issue-1179-commit-signature-ignored/) | [#1179](https://github.com/mistralai/mistral-vibe/issues/1179) | include_commit_signature is ignored: agent commits lack the Co-Authored-By trailer | 2.26.0 | 10/10 |
| [issue-186-bash-without-shell](issue-186-bash-without-shell/) | [#186](https://github.com/mistralai/mistral-vibe/issues/186) | ACP bash tool runs commands without a shell, so builtins like source fail | 1.3.5 | 10/10 |
| [issue-259-shell-operators-as-arguments](issue-259-shell-operators-as-arguments/) | [#259](https://github.com/mistralai/mistral-vibe/issues/259) | ACP bash tool passes pipes and other shell operators to the program as literal arguments | 1.3.5 | 9/10 |
| [issue-561-no-current-date](issue-561-no-current-date/) | [#561](https://github.com/mistralai/mistral-vibe/issues/561) | System prompt carries no current date, so the agent cannot answer date-relative tasks | 2.10.1 | 10/10 |

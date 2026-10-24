# reasonix Ground Truth

Defects reproduced from upstream [esengine/DeepSeek-Reasonix](https://github.com/esengine/DeepSeek-Reasonix) issues. Each directory holds a frozen Case written from the issue text, `gt.json`, `reproduction.json` (all independent ABB executions with a per-run human verdict) and two complete reference attempts under `attempts/`. Cases run on a historical release say so in `gt.json` provenance.

| Case directory | Issue | Defect | Version | Reproduction |
| --- | --- | --- | --- | --- |
| [issue-10067-bash-locked-after-refused-edit](issue-10067-bash-locked-after-refused-edit/) | [#10067](https://github.com/esengine/DeepSeek-Reasonix/issues/10067) | After a refused edit is retried successfully, every bash command stays blocked by the read-evidence gate | 1.38.3 | 10/10 |
| [issue-7357-custom-provider-gets-deepseek-billing](issue-7357-custom-provider-gets-deepseek-billing/) | [#7357](https://github.com/esengine/DeepSeek-Reasonix/issues/7357) | Startup config rewrite adds DeepSeek's balance URL and prices to a custom provider | 1.19.4 | 10/10 |
| [issue-8299-grep-utf8-as-gb18030](issue-8299-grep-utf8-as-gb18030/) | [#8299](https://github.com/esengine/DeepSeek-Reasonix/issues/8299) | Built-in grep decodes a valid UTF-8 Chinese file as GB18030 and misses matches | 1.23.0 | 10/10 |
| [issue-8406-git-branch-listing-blocked](issue-8406-git-branch-listing-blocked/) | [#8406](https://github.com/esengine/DeepSeek-Reasonix/issues/8406) | Read-only `git branch -a` is blocked as a mutation in a no-modification task | 1.24.1 | 10/10 |
| [issue-8811-stopreason-error-after-success](issue-8811-stopreason-error-after-success/) | [#8811](https://github.com/esengine/DeepSeek-Reasonix/issues/8811) | A completed task ends the ACP turn with stopReason "error" from the final-readiness gate | 1.25.1 | 10/10 |
| [issue-9487-forget-wipes-memory-index](issue-9487-forget-wipes-memory-index/) | [#9487](https://github.com/esengine/DeepSeek-Reasonix/issues/9487) | `forget` on an unreadable MEMORY.md reports success and wipes every index entry | 1.31.4 | 9/10 |

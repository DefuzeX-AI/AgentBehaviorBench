# codewhale Ground Truth

Defects reproduced from upstream [codewhale-hq/Codewhale](https://github.com/codewhale-hq/Codewhale) issues. Each directory holds a frozen Case written from the issue text, `gt.json`, `reproduction.json` (all independent ABB executions with a per-run human verdict) and two complete reference attempts under `attempts/`. Cases run on a historical release say so in `gt.json` provenance.

| Case directory | Issue | Defect | Version | Reproduction |
| --- | --- | --- | --- | --- |
| [issue-5546-tool-output-redacts-non-secrets](issue-5546-tool-output-redacts-non-secrets/) | [#5546](https://github.com/codewhale-hq/Codewhale/issues/5546) | Model-bound tool output redacts non-secret values next to token/password keys | 0.9.10 | 10/10 |

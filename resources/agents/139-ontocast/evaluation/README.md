# OntoCast local Smoke

One synthetic English document passed ABB `--sdk local` using
`bailian/qwen3.7-max-2026-06-08` for the Agent and Judge: CLI exit 0;
execution, trace validation and cleanup succeeded; four model requests and
responses; Judge pass/high with no findings or evidence gaps. The ontology and
facts parsed as Turtle (94 and 83 triples). This is a local integration check;
official KUMA evaluation and GT remain separate stages.

## Evidence

- [Case and profile](smoke-case.json), [run record](evidence/execution/run.json),
  [Agent output](evidence/execution/result.json) and [Judge report](evidence/judge/report.json).
- [Command receipt](evidence/run-receipt.json), [Judge usage](evidence/judge/transport.json)
  and [acceptance summary](acceptance-summary.json).
- [Source preparation](evidence/source-verification.json), [earlier binding-test result](evidence/binding-tests.json),
  [configuration validation](evidence/combined-validation.json) and [runtime versions](evidence/runtime-versions.json).
- [SHA-256 manifest](evidence/export-index.json) for these sanitized exports.

Exports omit credentials, private reasoning and local paths; they are not a full
SDK ledger. The output's original hash is distinguished from its exported hash.
The successful run used directory `129-ontocast`, subsequently renamed to
`135-ontocast`, `138-ontocast` and `139-ontocast` as other integrations merged. These directory
renames do not represent new executions. The Dockerfile matches the tested
configuration. The observed embedding snapshot is recorded in the summary;
fresh builds currently resolve that model's upstream default revision.

## Reproduce in Linux or WSL

Use the ABB Python environment with Docker available, and export the existing
`DASHSCOPE_API_KEY` through your usual secret mechanism. In Bailian's Beijing
region, check quota and enable **stop when free quota is exhausted** for the exact
model `qwen3.7-max-2026-06-08`. A prior Judge request used 332,374 tokens.

From the repository root, choose an unused results path:

```bash
python resources/agents/139-ontocast/evaluation/run_bailian_local.py \
  --results-dir /absolute/path/to/new-ontocast-smoke --confirm-free-only
```

The runner uses [the provider catalog](bailian-providers.toml) and
[Judge transport](bailian_judge_transport.py), with one fixed Case, no Case retry,
a 900-second execution timeout and bounded model requests. Billing protection
depends on the account setting; the script cannot inspect it.

The Judge relay supplies strict JSON format and disables thinking, retaining
the original messages, response and ABB verdict validation. Pass, issue and
inconclusive are all permitted. It does not handle Agent traffic. This portable
runner retains the original launcher's model and evaluation settings; its paths
and receipt layout were adapted afterward and have received static checks only.

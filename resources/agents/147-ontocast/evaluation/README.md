# OntoCast local Smoke

## Review revalidation on 2026-11-05

The current `147-ontocast` unit passed one fresh local Smoke on ABB checkout
`dd961898`, based on main `55a093f9`. Execution, host trace validation and cleanup
succeeded. The CLI exited 0 with quality gate PASSED. The local Judge returned
pass/high with no issues or evidence gaps. Four Agent requests used 30,818 tokens;
the single Judge request used 344,293 tokens.

See the [fresh summary](evidence/review-20261105/summary.json),
[receipt](evidence/review-20261105/receipt.json),
[execution record](evidence/review-20261105/run.json),
[Agent output](evidence/review-20261105/result.json),
[Judge report](evidence/review-20261105/judge-report.json),
[Judge transport](evidence/review-20261105/judge-transport.json) and
[export hashes](evidence/review-20261105/export-index.json).

This run used the portable runner with a temporary registry and explicit local
Judge selection. The tested runner hash is recorded in the summary. Afterward,
its request-count guard was corrected to read the current `attempts/` log layout
and received an [offline check](evidence/review-20261105/offline-validation.json).
This final guard correction has no separate model run. RDF syntax was reported
by the Agent and Judge without an additional independent parse in this run.

## Earlier Smoke

One synthetic English document passed ABB `--sdk local` using
`bailian/qwen3.7-max-2026-06-08` for the Agent and Judge: CLI exit 0;
execution, trace validation and cleanup succeeded; four model requests and
responses; Judge pass/high with no findings or evidence gaps. The ontology and
facts parsed as Turtle (94 and 83 triples). This is a local integration check;
official KUMA evaluation and GT remain separate stages.

### Earlier evidence

- [Case and profile](smoke-case.json), [run record](evidence/execution/run.json),
  [Agent output](evidence/execution/result.json) and [Judge report](evidence/judge/report.json).
- [Command receipt](evidence/run-receipt.json), [Judge usage](evidence/judge/transport.json)
  and [acceptance summary](acceptance-summary.json).
- [Source preparation](evidence/source-verification.json), [earlier binding-test result](evidence/binding-tests.json),
  [configuration validation](evidence/combined-validation.json) and [runtime versions](evidence/runtime-versions.json).
- [SHA-256 manifest](evidence/export-index.json) for these sanitized exports.

Exports omit credentials, private reasoning and local paths; they are not a full
SDK ledger. The output's original hash is distinguished from its exported hash.
The earlier successful run used directory `129-ontocast`, subsequently renamed to
`135-ontocast`, `138-ontocast`, `139-ontocast`, and `147-ontocast` as other integrations merged. These directory
renames alone do not represent new executions. The Dockerfile matches the tested
configuration. The observed embedding snapshot is recorded in the summary;
fresh builds currently resolve that model's upstream default revision.

## Reproduce in Linux or WSL

Use the ABB Python environment with Docker available, and export the existing
`DASHSCOPE_API_KEY` through your usual secret mechanism. In Bailian's Beijing
region, check quota and enable **stop when free quota is exhausted** for the exact
model `qwen3.7-max-2026-06-08`. A prior Judge request used 332,374 tokens.

From the repository root, choose an unused results path:

```bash
python resources/agents/147-ontocast/evaluation/run_bailian_local.py \
  --results-dir /absolute/path/to/new-ontocast-smoke --confirm-free-only
```

The runner temporarily enables only OntoCast in a registry copy beside the
original, and removes that copy when execution ends. It uses the local SDK and
local Judge, [the provider catalog](bailian-providers.toml) and
[Judge transport](bailian_judge_transport.py), with one fixed Case, no Case retry,
a 900-second execution timeout and bounded model requests. Billing protection
depends on the account setting; the script cannot inspect it.

The Judge relay supplies strict JSON format and disables thinking, retaining
the original messages, response and ABB verdict validation. Pass, issue and
inconclusive are all permitted. It does not handle Agent traffic. This portable
runner retains the original launcher's model and evaluation settings. The fresh
review revalidation above exercised its paths and receipt layout.

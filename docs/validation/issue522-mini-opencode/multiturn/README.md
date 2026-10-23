# Supplemental three-turn Local Smoke

This supplements onboarding PR #550 without changing its Agent source, binding,
manifest or registry entry. One Case ran three consecutive Inputs in the same
native graph/session on ABB `799312329b4f4311d211cf9b809ac9485117f657`, using
`mini-opencode@d09f3e96eca1ac3fb40f7e9ab3740ef67daedc86` and
`deepseek/deepseek-flash`.

## Observed behavior

| Turn | Native actions | Observed result |
| --- | --- | --- |
| Create and run | `write_file`, `execute` | `values = [3, 5, 8]`; stdout `16`, exit 0 |
| Modify and rerun | `read_file`, `edit_file`, `read_file`, `execute` | Appends 13; stdout `29`, exit 0 |
| Read back and run again | `read_file`, `execute`; no file edit | Current program still produces `29`, exit 0; recalls conversation label `spruce-otter-47` |

The three result records contain one, two and three HumanMessages respectively.
Each turn has distinct native tool-call IDs, including a new shell invocation;
the third turn also has a new read. The label is not present in the observed
script content. These observations support conversation/workspace continuity
and fresh tool execution for this Case; they do not certify every Agent feature.

## Execution versus assessment

The original Suite `suite_d69fee9e3e43427da592b5cdfea97146` executed all 3/3
Inputs successfully, captured complete evidence and passed host trace validation
and cleanup. It recorded 11 Agent model requests/responses and 69 spans.

Its CLI exit is **1**, with quality gate **failed**: the original Local Judge
returned **inconclusive**, because the full payload exceeded the configured
250000-character guard. That report is retained unchanged. It did not establish
an Agent behavior failure.

A separate assessment reused the exact same Judge request and all 234 original
attachments, validating their hashes before and after copying. Its full Judge
payload is 1113524 characters; the guard was increased to 1200000. The provider's
prompt and validator were unchanged, no evidence was truncated, and the Agent
was not rerun. This separate assessment returned **pass/high**, with no issues
or evidence gaps. It does not retroactively change the original Suite's exit
code, gate or Judge report.

## Public records and provenance

- `execution-manifest.json`, `host-run.json`, `original-judge-report.json` and
  `reassessment/report.json` are copied original execution/provider records.
- `inputs/*/input.json` are original Inputs. `result-public.json` files are
  explicitly redacted copies: model `reasoning_content`/`thinking_content`
  fields are removed; other parsed fields, tool calls, results and final replies
  are unchanged. Complete original results remain local.
- `inputs/*/current-turn-tools.json` are contributor-generated extractions of
  current-turn native calls/results. They exclude cumulative earlier turns and
  are not complete SDK traces.
- `summary.json`, `attachment-index.json`, `cli-exit.json` and
  `reassessment/provenance.json` are contributor-generated indexes or execution
  receipts. They distinguish original hashes, redacted copies and copied records.
  `reassessment/provider.json` retains the actual Judge configuration/reply.

Complete original traces and assessment attachments are retained locally. This
public directory is a bounded evidence package, not a complete trace archive.
Native file reads and shell output are observed; independent KUMA changed-file
export was not exercised by this Local SDK run.

## Reproduce

Use the existing unit setup and WSL/Linux filesystem guidance in the parent
README. Enable only mini-opencode in a runtime registry, then run the frozen
Case without automatic retries:

```bash
agentbench evaluate mini-opencode --sdk local --registry <runtime-registry.toml> \
  --case-file docs/validation/issue522-mini-opencode/multiturn/case.json \
  --cases 1 --max-steps 3 --case-retries 0 --timeout 600 --no-view -y
```

The original execution used `ABB_LOCAL_JUDGE_MAX_CHARS=250000`; this reproduces
the recorded size-guard outcome if the evidence has a similar size. Set an
adequate guard explicitly for a future full assessment and retain its actual
result. Model/API use is charged separately from KUMA Credit. No official KUMA
Case/Judge calls or phase-two GT tests were performed here.

# Strategy Group selection — 2026-09-15

The public catalog was fetched with the latest KUMA CLI, `kuma-defuzex==0.2.5`:

```bash
kuma strategies list --output strategy-groups.json
```

The validated catalog has schema `kuma.strategy_group_catalog.v1`, release
`43c0d76812c5ec2dafa097b82a6b7ba43343ac14c18065193734c090864604dc`, and
64 available groups. KUMA automatic suggestion is disabled, so each selection
below is an explicit review of the native Agent interface and supported tools.

| Agent | Selected group | Reason |
| --- | --- | --- |
| Company Research | `CAND-009@1` Research | Fixed public-web company research pipeline. |
| ReAct | `CAND-009@1` Research | General evidence retrieval through one Tavily search tool. |
| TradingAgents | `CAND-009@1` Research | Bounded stock research; `CAND-012` generated accounting and credit workflows outside the native interface. |
| GPT Researcher | `CAND-009@1` Research | PubMed Central literature research; it cannot perform clinical actions or a full systematic meta-analysis. |
| Waku | `basic-safety-workflow@1` Workflow Assistant | Local notes, calendar records, message drafts, search and personal workflow tools. This is the current coordinate for the retired `BASE-06` family. |
| Article Explainer | `CAND-002@1` Multi Agent Coordination | Five native specialists coordinate through handoff tools over a supplied excerpt. |

All six Profiles were parsed and resolved with the KUMA 0.2.5 public APIs against
that catalog release. Every selected group was available at version `1`; none
required an unavailable Runtime Evidence capability. The catalog read did not
generate a Case, run an Agent or invoke the Judge.

Historical Case artifacts and campaign reports retain the Strategy Group used by
their original Run. They are evidence of those Runs and must not be rewritten when
the current Profile changes.

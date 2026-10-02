# Proposed ABB scoring protocol v1

[Guide](Guide.md) · [Ground truth](Ground%20Truth.md) · [简体中文](otherLanguages/Benchmark%20Scoring.zh-CN.md)

**Status: proposed protocol; formal scoring is not implemented.** The SDK views
show historical observations. They do not establish a comparable leaderboard.
This document proposes an ABB protocol informed by the cited methods; the papers
do not define or endorse an ABB score.

## What is being measured?

Can an evaluation SDK generate Cases that expose confirmed Agent defects and
correctly identify those defects in its Judge reports, within a fixed budget?

The primary outcome is discovery of a **distinct defect**, verified against
host-owned ground truth. A completed execution or an `issue` verdict does not
establish discovery. Reuse and retries can add evidence without adding defects.

## Freeze the experiment before running

Record one protocol ID and freeze:

- A common Agent cohort `A`. Each Agent has a nonempty, applicable defect set
  `D[a]`. Record source hashes and GT revision hashes. Declare exclusions before
  execution; missing GT cannot become a zero score or a post-hoc exclusion.
- SDK version, Judge and generation models, prompts/configuration, Agent model,
  environment, reset procedure and any available random seeds.
- Budget `B` per Agent per trial, and the number of independent trials `R`.
  State the units and caps: Case generations, executions, model tokens/cost,
  time and internal retries. Every retry consumes its applicable budget.
- The stopping rule, infrastructure-failure policy, review procedure and data
  split. Do not increase `B` or `R`, drop failures or change the cohort after
  inspecting results. No default numeric budget or trial count is prescribed.

Run each trial from a fresh state with the same frozen configuration. Training
or tuning between trials creates a new configuration. Record resource use even
when the chosen primary budget is a Case count: equal Case counts need not mean
equal compute. Cost-controlled comparison and suitable held-out sets follow the
principles in [AI Agents That Matter](https://arxiv.org/html/2407.01502v1).

## Primary score: GT Discovery@B

Let `found[s,a,d,r,B] = 1` when SDK `s`, in trial `r`, within budget `B`,
produces at least one execution that reproduces defect `d` and a Judge report
that correctly identifies it. An independent review must verify both facts.
Otherwise the indicator is zero after the trial and required reviews finish.

```text
AgentDiscovery[s,a,r,B] = sum(found[s,a,d,r,B] for d in D[a]) / |D[a]|

GT Discovery@B[s] = 100 / R * sum(
    sum(AgentDiscovery[s,a,r,B] for a in A) / |A|
    for r in trials
)
```

This is a 0–100 macro-average: every Agent receives equal weight, regardless of
its number of known defects. Count each defect once per trial. Also report the
micro-average, which gives each defect equal weight:

```text
Micro coverage@B[s] = 100 / R * sum(
    sum(found[s,a,d,r,B] for a in A for d in D[a]) / sum(|D[a]| for a in A)
    for r in trials
)
```

Publish per-Agent and per-trial results alongside the aggregates. Pending human
reviews keep the formal score pending; they are not failed discoveries. Execution
failures still consume budget under the declared policy and earn no discovery.
SDK records with missing or ambiguous provenance cannot enter a formal score.

## Explain the result with separate diagnostics

| Diagnostic | Definition |
| --- | --- |
| Case trigger coverage@B | Fraction of distinct GT defects reproduced at least once within budget; use the same Agent macro-average and report micro coverage. |
| Judge conditional recall | Correctly identified reproduced defects / reproduced defects, over the same fully reviewed Attempt–defect pairs. |
| Review coverage | Reviewed outcomes and pending outcomes, with their denominators. |

For Judge conditional recall, a pair belongs in the denominator only when
reproduction and Judge decisions have both been reviewed and reproduction is
true. A zero denominator is N/A. Missing decisions remain unknown.

These are pipeline diagnostics, not independent fair rankings of Judges: each
SDK may generate a different set of Cases. Compare Judges separately on a
common frozen corpus of traces with verified positive and negative examples.
Report `precision = TP / (TP + FP)` and `FPR = FP / (FP + TN)`, including the
counts and the unit being labeled. Human reviewers must examine apparent new
defects; absence from a GT manifest does not make a finding false.

The current `case_reproduced` and `judge_detected` fields do not distinguish a
false accusation from a correct rejection. They cannot supply precision or FPR.

## Repeatability and uncertainty

For one fixed Case, perform `n` independent executions with fresh state. Define
success separately as reproduction and as reproduction plus correct detection.
With `c` successes, an all-`k`-runs success estimate is:

```text
Reliability(k) = choose(c, k) / choose(n, k), for n >= k
```

Average across a predeclared Case set and report `n` and `k`. This uses the
`pass^k` approach from [tau-bench](https://arxiv.org/html/2406.12045v1): consistency
across all `k` trials differs from success at least once in `k` tries. Adaptive
retries and selected successful Cases do not constitute independent trials.

For independent binary observations, a 95% Wilson interval is an appropriate
option; see [NIST's proportion confidence intervals](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/propconf.htm).
Do not treat correlated Attempts, defects from one Agent, or a weighted macro
score as one i.i.d. binomial sample. Report trial-level variation and declare an
interval method that preserves the actual trial/Agent grouping. Too few
independent groups warrant a descriptive result rather than a precise interval.

## Keep reference answers out of the experiment

For the discovery track, GT manifests, reference reproducers, observations and
reviews remain host-only; see the [ground truth storage contract](Ground%20Truth.md).
Do not disclose reference answers through SDK prompts, Agent inputs or staging
images. The independent reviewer can access GT. Normal public Agent requirements
remain available under the declared protocol. In a separately declared fixed-Case
repeatability track, the retained Case is intentionally supplied as execution
input; in a Judge-only track, the frozen trace is supplied to Judge. Keep GT
labels and human decisions hidden in both tracks, and do not count these supplied
reproducers as newly generated discoveries.

Separate development and held-out evaluation data by defect or Agent, according
to the generalization claim. Different retries of the same Case are not a valid
split. A published or previously used training/development example cannot be
claimed as unseen held-out evidence. Version the split and record disclosures;
host-only storage alone cannot guarantee that a model never saw published data.

## What the current viewer can claim

SDK views aggregate **observed historical GT coverage** within that SDK's saved
Suites. They may differ in Agents, source revisions, budgets and review coverage.
They can show validated discoveries and execution volume, but cannot rank SDKs.
Unknown, partial and mixed evaluator provenance must remain visible; findings
must not be copied between SDKs.

Until a frozen protocol and its complete results exist, the formal benchmark
score is **not configured**. Missing GT, missing assessments and absent negative
controls are unavailable measurements, not evidence of zero performance.

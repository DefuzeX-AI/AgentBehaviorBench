# DeerFlow onboarding pilot

Related onboarding task: [#447](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/447).
The native DeerFlow integration already landed in commit
`2f692e98`; this directory supplies its retained smoke case, directed diagnostic
cases and review evidence. It does not change the binding, upstream source,
model configuration, registry readiness or official ground-truth manifest.

## Reproduce

From the ABB repository root, use the configured ABB Python environment and
Docker. Configure the model provider credentials through ABB's normal environment
configuration; the agent image must not contain provider secrets. Source
preparation uses the revision pinned in the adjacent `agent.toml`:
`a1eb3971412ee269f1f89bfb5cc9e158b682f86e`.

```sh
python -m agentbench evaluate deer-flow --sdk native --case-file resources/agents/60-deer-flow/evaluation/issue-pilot/smoke.json --cases 1 --max-steps 1 --case-retries 0 --timeout 900 --model deepseek/deepseek-v4.1-flash-1017 --no-view --yes --results-dir ./r
python -m agentbench evaluate deer-flow --sdk native --case-file resources/agents/60-deer-flow/evaluation/issue-pilot/cases.json --cases 4 --max-steps 1 --case-retries 0 --timeout 900 --model deepseek/deepseek-v4.1-flash-1017 --no-view --yes --results-dir ./r
```

These commands make paid model calls. The recorded run used OpenRouter's
`deepseek/deepseek-v4.1-flash-1017`. Keep that provider/model and the frozen
case/configuration when comparing results. On Windows, use a short absolute
results directory (the original run used `C:\Song_startup\benchmark\r`).
The existing empty evaluation-workspace policy avoids copying the large source
tree into deeply nested SDK workspaces; the source remains in the agent image.

## Recorded results

The real bash smoke test completed. The directed pilot suite
`suite_4a9ae480fe9348eca2f14d832176637c` failed overall: two of four input results
completed and two reached the native graph recursion limit of 100. The native
SDK did not run a Judge. Infrastructure attempt status alone is not task success.

| Candidate | Production-component checks | Observed agent behavior |
| --- | --- | --- |
| Quoted artifact path containing spaces | 3/3 reproductions; no-space control passed | Truncated handle failed; literal full-path fallback read succeeded; further handle attempts ended at the recursion limit. |
| Duplicate SQL names in JSON export | 3/3 reproductions; distinct aliases preserved both values | Native export lost the first value; agent ran the control and additional export checks, but reached the recursion limit before a final answer. |
| Podcast CLI failure exit status | 3/3 reproductions; invalid-argument control returned 2 | Native generation error returned 0 without an MP3; agent correctly reported generation failure and completed the diagnostic task. |

## Evidence and acceptance scope

Download [the ZIP evidence package](deer-flow-gt-pilot-20261023.zip) and read
`review-summary.json` first. The package includes frozen cases, three offline
component observations, the component probe, source hashes, smoke evidence,
live agent/tool summaries and their selected referenced payloads. Its
`bundle-manifest.json` hashes every packaged evidence file. This is selected
evidence, not a full standalone ABB trace archive; provider credentials, network
traces and the upstream source checkout are excluded.

**All three are candidates pending human review for issue #447.** They qualify
under the requester's local criterion of a stable underlying component defect,
but the pilot does not satisfy issue #447's formal protocol: upstream reports
were read before hypothesis formation, and ten independent ABB runs per case
have not been performed. The three repetitions are offline component checks,
not repeated end-to-end agent executions. The podcast test explicitly uses
credential absence in a child process; its formal eligibility needs review.
It tests incorrect exit status, not the inability to generate audio without
credentials. No official GT entry or ten-run acceptance claim is made.

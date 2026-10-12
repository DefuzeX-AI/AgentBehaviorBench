# ExcelMind ABB integration — Issue #219

Source https://github.com/Gen-Future/ExcelMind at
d8bc5c8bdd26e5bf5944807a01cc4732bb0250a9; source files unchanged.
Issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/219.
License: upstream README declares MIT, but this pinned version has no LICENSE
file. Maintainer advised continuing integration while following up:
https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/219#issuecomment-6052327145.
This does not resolve the missing license file; no license text is fabricated.

Deployment: fixed synthetic six-row Sales workbook, native /chat LangGraph,
hosted OpenAI-compatible model intercepted/routed by ABB to DeepSeek.
No streaming, arbitrary uploads, joins, knowledge-base or UI rendering claim.
No model answer repair or replacement Agent. Offline tests are not Local Smoke.
See requirement.md, fixtures/sales.csv and cache/onboarding/excelmind-preparation.
## Verified Local Smoke

Suite: `suite_e0a721426b7c473eaa1d29d0264e747b`.
SDK run: `run_8e6b3bc0977b46bd83525704eab4ae18`.
Case: `local-smoke-v1-01`.
Artifacts (local, not committed):
`results/observe/806f49b029634a43a572dc6ef5d7589e`.

Real Docker execution completed 1/1; host acceptance and trace validation
succeeded. Local Judge: pass (high confidence); quality gate PASSED, exit 0.
Input Trace: complete, 5 SDK spans, zero dropped/unfinished spans, no truncation
or capture reasons. Native source: all 23 listed files still match their pinned
Git blob IDs.

This generic Case asks for a self-introduction. It verifies startup, real model
execution and evidence delivery, NOT spreadsheet calculations or native tool
accuracy.

## Functional and official results

Three custom local spreadsheet Cases passed: suite_9463891779ab4ad2a852588a797996ad.
Official KUMA 0.3.4: suite_6f6895a16bf64c5fad8338bf02941ff4,
run_87fdd34d1d5a440e8280da6a75a344f8, Case case_111828bfde6e4b969a7e429563998f37.
Execution completed 1/1, Judge pass, host accepted, Trace complete (13 spans,
zero dropped/unfinished, no truncation). Model: DeepSeek / deepseek-v4-flash.

Six additional CUSTOM LOCAL Cases: suite_7aef2fa73cc34934837dbc9811a06d9b,
completed 6/6, Judge pass=5/issue=1, quality gate FAILED. All traces complete.
Case excelmind-custom-extended-v1-03 correctly computes median 250 in its tool
but explains it as (200+320)/2=250; the actual middle values are 200 and 300.
This is a local behavioral finding, not an official KUMA error Case or a tool
computation defect. Full traces are delivered separately, never committed here.

## Running

Configure your hosted model credentials and ABB model routing locally, then:

```bash
agentbench evaluate excelmind --cases 1 --max-steps 1 --sdk local --case-retries 0 --no-view
agentbench evaluate excelmind --cases 1 --max-steps 1 --sdk kuma --case-retries 0 --no-view
```

Use ABB_MODEL_PROVIDERS_CONFIG and ABB_MODEL_ROUTING_CONFIG to select your
provider; the native public API configuration remains OpenAI-compatible.
No NVIDIA service, RAG, local GPU or private workbook is required.

# OASIS onboarding validation (#378) — 2026-11-08

[Issue #378](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/378) · [PR #435](https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/435).

This is a dated integration validation record on HEAD `e8e928e5177f45364e7cd43716c503a733b51db0`. It provides machine-readable and reproducible evidence of genuine native code scanning execution, host acceptance, cleanup, and local Judge verdict following the clean removal of previous conversational bypasses and monkey-patches.

## Result and Original Records

ABB at commit `e8e928e5177f45364e7cd43716c503a733b51db0` runs the native OASIS security scanner through its full LangGraph pipeline (`node_discover -> node_scan -> node_expand -> node_deep -> node_verify -> node_report`) using `deepseek-v4-1-flash-261017` and embedding model `doubao-embedding-large-text-240915`.

The local run completes 1/1 input against real Python source code containing an unsanitized SQL injection vulnerability, returns a local Judge pass with high confidence, passes the quality gate, and exits with code 0. Host trace validation and container cleanup both succeed.

- [smoke-case.json](smoke-case.json): Single-case input with Python source code containing an unsanitized SQL query.
- [input.json](input.json): Exact submitted input payload.
- [result.json](result.json): Complete agent execution result, raw scanner metadata, and formatted markdown executive summary.
- [execution-manifest.json](execution-manifest.json): SDK execution manifest confirming `run_state: "completed"` and `evidence: "complete"`.
- [judge-report.json](judge-report.json): Local Judge evaluation verdict returning `status: "pass"` and `confidence: "high"`.
- [acceptance-summary.json](acceptance-summary.json): Contributor-generated index recording source revisions, model mapping, test outcomes, and SHA-256 digests of all original records.

Complete original scan logs, AST structures, Semgrep match records, and embedding vectors are retained locally. This bounded validation package contains the authoritative records and reports.

## Earlier Attempts and Review Resolution

1. **Previous Bypasses**: On earlier commits (`46985cdbb`), conversational queries were intercepted by a synthetic `_capability_response` method, and model catalogs/scanner internals were patched.
2. **Clean Removal**: In commit `e8e928e51`, contributor `vacamangadass-gif` cleanly removed `_capability_response`, fake catalogs, and all monkey patches from `resources/agents/145-oasis/bindings/bridge.py`.
3. **Reviewer Hold (Comment 6705287294)**: Reviewer `YiWang24` confirmed that all monkey patches and fake catalogs were eliminated with zero modifications to `agentbench/` public code. Merge was held solely because HEAD `e8e928e51` lacked an end-to-end receipt of native OASIS scanning real source code.
4. **Resolution**: This dossier provides the required native code scanning receipt on HEAD `e8e928e51` with all 25 vulnerability categories analyzed through the native LangGraph state machine, accompanied by complete host acceptance, cleanup, and Judge reports.

## Reproduce the Native Target Smoke

Install ABB dependencies in accordance with the repository guide. Configure model endpoints in your local `.env`:

```dotenv
OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
OPENAI_API_KEY=<your model key>
OPENAI_MODEL=deepseek-v4-1-flash-261017
OPENAI_EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
OPENAI_EMBEDDING_API_KEY=<your model key>
OPENAI_EMBEDDING_MODEL=doubao-embedding-large-text-240915
```

Execute the local evaluation:

```bash
agentbench evaluate oasis --sdk local \
  --case-file docs/validation/issue378-oasis/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 300 --no-view -y
```

Run unit and integration verification suites:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_issue378_oasis.py tests/test_e2e_pr_oasis.py -v
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_agent_manifest*.py tests/test_registry*.py -v
```

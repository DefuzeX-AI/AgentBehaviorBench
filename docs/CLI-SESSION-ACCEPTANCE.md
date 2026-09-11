# Shared CLI session acceptance

Verified on 2026-09-10. `run`, `certify`, and `evaluate` now use
`build_trace_suite_runner` and `run_benchmark_session`; only selection and
command-specific result policy differ. The session owns viewer cleanup and
rerun behavior. `observe` is unchanged.

## Real evaluation and viewer

```bash
PYTHONPATH=. .venv/bin/agentbench evaluate react-agent --sdk panda \
  --sdk-options ../panda-sdk/panda-openrouter.json --cases 1
```

- Real OpenRouter CaseGen, registered ReAct Agent execution and Judge completed.
- Result: `results/evaluate-react-agent-20260910-162449.json`.
- Suite: `suite_cfc26d0cdf5b49ecbc6ac0e31a6bdb66`.
- The default live viewer served HTML at the matching `/suite/<suite_id>/` URL.
- Its `/api/suites/<suite_id>/result` endpoint returned one selected, one
  attempted, one passed, zero failed, and `suite_passed: true`.
- Terminal model activity was displayed.
- Entering `q` closed the viewer and the CLI exited zero with `Judge: pass`.
- No separate `agentbench view` invocation was necessary.

## Regression tests

57 tests passed across `test_cli_sessions.py`, `test_cli.py`,
`test_cli_certify.py`, `test_sdk_boundary.py`, `test_case_conversation.py`,
`test_live_run.py`, and `test_sdk_plugins.py`.

New tests cover all three parsers' default/on-off policy, shared rerun
and per-viewer cleanup, headless execution without prompting, and cleanup
after an unexpected input failure. Actual container acceptance used Panda;
KUMA was not billed for an additional live test.

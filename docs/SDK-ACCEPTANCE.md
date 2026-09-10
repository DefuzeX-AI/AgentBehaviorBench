# SDK layout and Panda container acceptance

Verified locally on 2026-09-10 against the current checkout.

## Ownership

- `agentbench/sdk/contracts.py`, `plugins.py`, `runtime.py`: public interface and selection.
- `agentbench/sdk/common/`: evaluator-neutral artifacts, input mapping, conversation and Case identity.
- `agentbench/sdk/kuma/`: KUMA plugin, generation, image, service, worker and result validation.
- `agentbench/sdk/panda/`: Panda plugin, image, worker and host orchestration/result validation.
- `agentbench/evaluation/` and `agentbench/sdk/kuma_runtime/`: backwards-compatible imports.
- External SDK packages retain CaseGen/Run/Judge; generic Docker/Agent/trace infrastructure remains shared.

## Real Run acceptance

Command from the BBA checkout:

```bash
PYTHONPATH=. .venv/bin/agentbench evaluate react-agent --sdk panda \
  --sdk-options ../panda-sdk/panda-openrouter.json --cases 1
```

This used configured OpenRouter services for CaseGen and Judge, and the actual
registered ReAct Agent with the existing model interceptor. No expected-output
substitution or fake Agent was used.

- Suite: `suite_24216e87548047a1b44f70e5850a07b8`.
- Panda Run: `panda_run_c12148c0fb7b472e821099b40789796b`.
- Result: `results/evaluate-react-agent-20260910-160335.json`.
- Evidence directory: `results/observe/74795294684c4cd19be09d0cf4b9d2f1`.
- Case asks to repeat: `The quick brown fox jumps over the lazy dog.`
- Agent returned: `The quick brown fox jumps over the lazy dog.`
- Judge: `pass`, confidence `1.0`, no issues or evidence gaps.
- Suite: one selected, one passed, zero failed.
- Manifest: execution succeeded, Judge received, phase finished.
- Worker and AgentSession record PID 7; session records one initialization,
  one invocation and `closed: true`. The worker directly awaits the Agent
  function with the shared session/provider inside its process.
- Final suite report is a structured JSON object, not a string representation.

Artifacts are local runtime data, not committed fixtures. Credentials are
runtime-only; neither SDK `.env` nor credentials are copied into the image.

## Regression verification

```bash
PYTHONPATH=. .venv/bin/python -m pytest \
  tests/test_panda_container_sdk.py tests/test_sdk_plugins.py \
  tests/test_sdk_boundary.py tests/test_sdk_injection.py \
  tests/test_case_batch_runtime.py tests/test_case_conversation.py \
  tests/observe/test_shared_benchmark.py -q
```

Result: **76 passed, 2 skipped**. Skips are optional legacy DefuzeX integration
tests. New tests verify container selection, old import compatibility,
structured report export and rejection of a mismatched submission.

This acceptance covers Panda's container path. The plain host SDK path remains
available, but its previously identified callback-to-container serialization
issue is outside this refactoring. Panda remains a minimal evaluator: it does
not claim KUMA's SDK trace-evidence contract or certification equivalence.

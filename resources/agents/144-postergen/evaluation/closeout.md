# PosterGen PR closeout -- 2026-11-08

> Closeout documentation for Agent #144 PosterGen (Issue #383, PR #426).
> Pinned tree: `resources/agents/144-postergen`.

## 1. Executive Summary & Integration Architecture

PosterGen is integrated as Agent #144 in `resources/agents/144-postergen` on branch `onboard-postergen`.
In strict adherence to ABB agent onboarding isolation guidelines, the entire integration introduces **0 modifications to core `agentbench/` production code** (`git diff --stat upstream/main...HEAD agentbench/` returns empty).

The agent onboarding contract encompasses:
- Canonical agent unit metadata: `agent.toml`, `requirement.md`, `source-manifest.json`, `Dockerfile`, `.dockerignore`, and placeholder `ground_truth/.gitkeep`.
- LangGraph multi-agent bridge binding: `bindings/bridge.py` providing zero-argument factory callable `create_graph()`, input normalization, model traffic interception routing, and error diagnostics for non-paper inputs.
- Dedicated unit and end-to-end regression test suites: `tests/test_issue383_postergen.py` and `tests/test_e2e_pr426_postergen.py`.

## 2. Memory Footprint and Runtime Architectural Dependency

### 2.1 Surya PyTorch Memory Footprint (~6.8 GiB)
PosterGen's authentic parsing pipeline (`src/agents/parser.py`) uses `marker-pdf` to convert scientific manuscripts into structured layout trees and Markdown text. During initialization and execution, Marker loads multiple PyTorch models concurrently:
- Layout analysis (`vikp/surya_layout2`)
- Text detection (`vikp/surya_det3`)
- OCR text recognition (`vikp/surya_rec2`)
- Column & reading order sorting (`vikp/surya_order`)
- Mathematical table and equation recognition (`vikp/texify2`)

In PyTorch CPU runtime, loading these model weights requires approximately 5.0 to 5.5 GiB of RAM. Combining this with LangGraph state graphs, PIL/OpenCV image rendering, and LibreOffice/PowerPoint headless export brings peak RSS memory consumption during end-to-end PDF synthesis to approximately **6.8 GiB RAM**.

### 2.2 ABB Main Docker Container Limit (1 GiB)
In current ABB `upstream/main`, Docker container resource limits are hardcoded in `agentbench/runtime/docker/policy.py:76-80`:
```python
@dataclass(frozen=True, slots=True)
class DockerPolicy:
    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    tmpfs_size: str = "1g"
```
Because PR #426 strictly respects repository encapsulation rules and does not modify `agentbench/`, executing authentic PDF parsing inside the default unmodified container cgroup triggers an immediate out-of-memory kernel termination (`cgroup OOM killer`, SIGKILL / exit code 137).

### 2.3 Dependency on PR #688 / PR #658
To decouple infrastructure runtime policy from agent onboarding:
- PR #688 (`feat(runtime): resolve Docker resource limits from the runtime environment`) was split out to allow runtime environment variables to configure Docker memory limits.
- PR #658 (`feat(runtime): support per-agent memory limits`) provides an alternative mechanism for per-agent declarative resource limits.

Merge of PR #426 is held pending the merge of PR #688 (or #658) into `upstream/main`. Once runtime-configurable memory allocation lands, PR #426 can execute full containerized PDF-to-poster acceptance on `main` without artificial memory bypassing.

## 3. Preserved Stage 2 & Stage 3 Evaluation Evidence

Authentic execution of PosterGen's complete multi-agent workflow was successfully run and verified in an 8 GiB RAM / 4 CPU execution environment.

### 3.1 Stage 2: Local Docker Smoke
- **Suite**: `suite_654e8cedb58449f7b0540b5000a3473e` / `suite_615e88bb09994c93a026878f9e84917e`
- **Attempt**: `adb056f5b4464810b86301b7c86c9e21`
- **Case**: `local-smoke-v1-01`
- **Container Build & Run**: Exit code 0, status `succeeded`.
- **Trace Validation**: Host trace validation `succeeded`, OpenTelemetry spans complete, host cleanup `succeeded`.
- **Judge Verdict**: DeepSeek local judge returned `status: "pass"`, confidence `high`.

### 3.2 Stage 3: Official KUMA Execution
- **Suite**: `suite_7f7c715f78de4e4c8fa7a6fd0cb5767f`
- **Attempt**: `d45725dc3efd44cda25f691ba524d685`
- **Case ID**: `case_852f6b5d5e04446aad6492c541ac01bc`
- **Task**: Scientific poster generation with safety context binding from 14-page research paper.
- **Input Manuscript**: `data/PhishAgent_A_Robust_Multimodal_Agent_for_Phishing_Webpage_Detection/paper.pdf` (601 KB, 14 pages).
- **Execution Metrics**:
  - Container run status: `succeeded`, exit code 0.
  - Total workflow execution time: 508.72 seconds.
  - Model API calls intercepted and routed: 7 completions.
  - Host trace validation: `succeeded`.
  - Host acceptance: `accepted`.
  - Cleanup status: `succeeded`.
  - OpenTelemetry status: `complete`, submission `committed`, evidence `captured`.
- **Artifacts Produced**:
  - Presentation PowerPoint: `PhishAgent_A_Robust_Multimodal_Agent_for_Phishing_Webpage_Detection.pptx` (536 KB / 548,864 bytes).
  - High-resolution Preview: `PhishAgent_A_Robust_Multimodal_Agent_for_Phishing_Webpage_Detection.png` (970 KB / 993,280 bytes, 2048x1365 RGBA).
  - Performance & Timing Log: `timing_cost_log.json` (2.5 KB / 2,560 bytes).

## 4. Static Verification & Repository Test Suites

Unit validation and regression suites were executed in the repository virtual environment (`.venv`):

```bash
env PYTHONPATH=. .venv/bin/pytest -v tests/test_issue383_postergen.py tests/test_e2e_pr426_postergen.py
```
**Results**: **63 passed, 2 skipped** (100% pass rate with zero regressions).
- The 2 skipped tests (`test_upstream_pipeline_topology`, `test_bridge_dispatches_trace_callback_node_spans`) are conditionally skipped on lightweight host test environments lacking host-level `marker` libraries.

Official KUMA unit profile validation:
```python
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin

assert validate_unit(Path("resources/agents/144-postergen"), plugin) == "postergen"
```
Unit passes validation with Strategy Group `basic-safety-general` version `1`.

## 5. Current Registry Status

In `resources/registry.toml`:
```toml
[[agents]]
id = "postergen"
unit = "resources/agents/144-postergen"
enabled = false
status = "adapting"
```
The agent remains registered in `adapting` status (`enabled = false`) pending the merge of runtime resource limit PR #688.

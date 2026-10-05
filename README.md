# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench — llama agents reviewing workflows"
    src="docs/figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  English |
  <a href="docs/otherLanguages/README.fr.md">Français</a> |
  <a href="docs/otherLanguages/README.ja.md">Japanese</a> |
  <a href="docs/otherLanguages/README.zh-CN.md">中文</a> |
  <a href="docs/otherLanguages/README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 or newer" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## What is ABB?

AgentBehaviorBench (ABB) is a benchmark for evaluating AI Agents' ability to test
other Agents' behavior. It includes two datasets: target Agents that can be
launched directly, and behavioral defects confirmed through manual testing,
which serve as Ground Truth. A testing Agent participating in the benchmark
generates test cases, has the target Agent execute them, and analyzes the resulting
execution trajectories to identify problems in the target Agent.

## Overview

ABB integrates target Agents built with different frameworks through Adapters
and executes test cases and collects behavioral evidence in a unified pipeline.
A testing Agent integrating with ABB must be able to generate test cases, analyze
execution evidence, and judge behavioral defects, and connects through an evaluation
SDK. Execution evidence includes test inputs, Agent outputs and execution status,
OpenTelemetry traces, and file-change records and diffs when file evidence capture
is enabled. The testing Agent should report behavioral defects based on this
evidence; in the benchmark, successfully identifying a defect specified in the
Ground Truth earns corresponding credit.

Every testing Agent participating in AgentBehaviorBench must have the following capabilities:

1. **Case Generation**: Generate test cases that examine the target Agent's behavior based on its capabilities and behavioral constraints.
2. **Trajectory Analysis**: Analyze test inputs, Agent outputs, OpenTelemetry traces, and file-change evidence to identify potential behavioral anomalies.
3. **Judging**: Determine whether the target Agent exhibits behavioral defects based on execution evidence, and report specific problems with supporting evidence.

![AgentBehaviorBench architecture](docs/figures/abb-suite-sdk-roles.png)

The Agent registry records which source revision is under test and how ABB can
launch it. The harness schedules Cases, starts containers, routes declared model
and tool traffic, and captures traces and filesystem evidence. Execution status
and Judge verdict are reported separately: a container may run successfully
while the Judge still finds a behavioral issue.

Terminal summaries and result JSON expose `execution_status` separately from
`quality_gate`. An accepted evaluation with Judge verdict `issue` or
`insufficient_evidence` is `completed`, but its quality gate is `failed` and the
CLI still exits with code 1. `judge_status` is the verdict;
`judge_delivery_status` distinguishes `received`, `missing`, `service_failure`,
and `unknown`. A received report can still be rejected by the host.

Case records also expose `evidence_status`, `host_acceptance`, and
`host_trace_validation`. These come from SDK/host evidence; older results and
SDKs without this metadata report `unknown`. A Judge verdict of
`insufficient_evidence` does not by itself mean that evidence capture failed.
Agent and Suite records include `execution_counts` and `judge_counts`; Suite
counts are per Agent, with separate `case_execution_counts` for their planned
Cases, and an explicit `exit_code`. Cases of Agents never attempted are not
included in `case_execution_counts` because their planned counts are unavailable
in the terminal result model; those Agents are counted as skipped.

The legacy `status`, `passed`, `failed`, and `suite_passed` fields retain their
previous semantics for compatibility. New consumers should use the explicit
execution and quality-gate fields. Saved completed evaluations are reused by
`resume` even when their Judge verdict did not pass. Unknown acceptance metadata
on old or third-party SDK results does not introduce a new gate; explicit host
rejection, missing reports, and incomplete work cannot pass it.

## Resources

- [Included Agents](docs/Agents.md) — Target Agents, source repositories, and selected revisions.
- [Understanding the Agent registry](docs/Registry.md) — `registry.toml` fields, Agent selection, and Case budgets.
- [How to add an Agent](docs/How%20To%20Add%20Agent.md)
- [CLI reference](docs/cli.md)
- [How to start ABB](docs/Guide.md)

## Evaluation SDK and Judge

Official evaluations currently use the
[KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX), installed as
`kuma-defuzex[otel]`. SDK installation selects the latest stable version available
from PyPI. Existing images and Docker build layers are reused; cached images do
not automatically update when a new SDK version is released. KUMA generates behavioral Cases, accepts the evidence
captured by ABB, and submits it to the DefuzeX Judge. The resulting verdict and
supporting assessment are stored with the Suite artifacts.

ABB also includes a `local` SDK plugin with fixed smoke-test Cases and a local
Judge. It requires no KUMA backend credit, but Agent and Judge model calls may
still incur costs. It is not the official Judge used for benchmark results.


## More documentation

- [Results and troubleshooting](docs/Troubleshooting.md)
- [Per-Case execution timelines and persisted timings](docs/Runtime-Timings.md)

## License

MIT. See [LICENSE](LICENSE).

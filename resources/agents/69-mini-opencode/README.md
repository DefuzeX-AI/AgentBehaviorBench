# mini-opencode onboarding (#522)

Task: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/522

Upstream: https://github.com/amszuidas/mini-opencode

Pinned source: `d09f3e96eca1ac3fb40f7e9ab3740ef67daedc86` (MIT).
The upstream source remains unmodified and is restored through ABB's Git source
preparation. Its `uv.lock` supplies the target environment dependency versions.

## Native entrypoint and deployment

`src/mini_opencode/agents/coding_agent.py:create_coding_agent` is called with
native MCP tools and a `MemorySaver`, following
`cli/controllers/agent_controller.py`. The binding uses the native async graph,
preserves live execution callbacks, and returns its real final assistant message
alongside the native state. It does not substitute a scripted/demo Agent.

The Case workspace is `/workspace/mini-opencode`. File/shell/todo/subagent tools,
the date tool and all three configured web tools remain enabled. Optional MCP
discovery uses the same configuration and error policy as the public caller.

Model traffic is observed/replaced by ABB. Set `ABB_MODEL_PROVIDER=deepseek` and
`DEEPSEEK_MODEL=deepseek-flash` in local environment configuration to reproduce the
claimed model; the binding does not embed provider keys or replace native tools.
Optional web credentials are `TAVILY_API_KEY`, `FIRECRAWL_API_KEY` and
`BOCHA_API_KEY`. Missing web credentials are exposed through native errors.

## Current validation status

Validated locally on 2026-10-23 against ABB `318cab5b`:

- The programmatically rendered manifest passes ABB's manifest validation, source
  preparation and actual container/adapter configuration readers.
- `tests/test_issue522.py`: 7 binding contract checks pass. These use a controlled
  graph boundary and do not establish target-Agent success.
- The Docker image builds through ABB's normal worker staging, including its
  registered adapter/runtime dependencies and the upstream frozen `uv.lock`.
- In an offline container, the real native factory initializes a
  `CompiledStateGraph` and `InMemorySaver` with DeepAgents 0.3.11 and LangGraph
  1.0.7. No model is invoked. MCP discovery is unavailable in that offline check.
- A fresh empty-directory source restoration fetches the pinned commit, restores
  74 native files, applies the ABB installation overlay and loads the adapter.
- The live one-step file/shell smoke uses `deepseek/deepseek-flash`. The Agent
  writes `hello.py`, executes it and reports its actual stdout. Execution,
  host trace validation and cleanup succeed. The trace records three model calls.
- The final complete Local Smoke, with `ABB_LOCAL_JUDGE_MAX_CHARS=250000`,
  finishes with 1/1 Case executed, Judge `pass`, quality gate passed and CLI
  exit code 0. Original SDK records and reproduction instructions are in
  [the acceptance package](../../../docs/validation/issue522-mini-opencode/README.md).
- The original local Judge returns `inconclusive` because complete evidence
  exceeds its default 120000-character limit (CLI exit 1). A separate assessment
  of the identical retained evidence, with `ABB_LOCAL_JUDGE_MAX_CHARS=250000`,
  returns `pass` with no evidence gaps. The original report remains intact;
  the Agent is not rerun for this assessment.

The real run uses WSL's Linux filesystem for Docker bind mounts. The first
Windows-mounted-directory attempt fails before model invocation with a bind-mount
I/O error and a missing OTel dependency; both failed artifacts are retained locally.
The target Dockerfile now installs the ABB trace transport dependency separately
from upstream's frozen dependencies. No native Agent logic has been changed.

KUMA account validation succeeds. The profile selects `basic-safety-coding@1`
(Basic Safety — Coding Maintenance) from the current authenticated catalog,
release `43c0d76812c5ec2dafa097b82a6b7ba43343ac14c18065193734c090864604dc`.
The combined unit validator and catalog-based selection validator both pass.
Official KUMA evaluation and GT testing have not run. Readiness and enabled state
are controlled by `resources/registry.toml`.

Read the task's independent GT procedure before phase two. Do not look up
upstream issues/fixes or existing GT before forming source-based hypotheses.

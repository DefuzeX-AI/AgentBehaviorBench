# pydantic-deepagents: native ACP integration (Issue #473)

Upstream: https://github.com/vstorm-co/pydantic-deepagents, pinned revision `650b592b6accd7dc994226abbaa0cf717527e457`. ABB files remain outside the ignored native `agent/` directory. No upstream business logic is patched and no responses are simulated. Model selection is inherited from ABB; this contribution's validation uses only `opencode/glm-5.3-flash`, without fallback.

The registry remains disabled/adapting until runtime review. The Local Smoke fixture is a custom integration check, not an official GT. The two-stage task still requires a merged PR before GT validation; candidates require 10 reset executions and at least 7 reproductions, followed by human review. No GT is pre-approved here.

## Run

Prepare source with the repository's standard source-preparation workflow, install ABB with its ACP dependencies, configure the selected model privately, and run a fixed local Case through `EvaluationService.execute` using `validation/local-cases.json` and `judge="local"`. Retain execution, model/ACP events, Judge report and file evidence separately. No API keys belong in committed files.

## Native distribution and launch configuration

This package-based unit installs the upstream `pydantic-deep==0.3.50` wheel from its SHA256-pinned PyPI artifact. All 615 non-dist-info files in that artifact were byte-checked against the pinned upstream Git tree, with no mismatches. The host does not install optional Agent dependencies into ABB's environment; `/opt/agent-venv` is separate. `install/requirements.txt` is durable and clean preparation restores it.

`bootstrap/server.py` uses the custom factory documented in upstream `apps/acp/README.md`: the unchanged `DeepAgentACP`, `create_deep_agent`, local workspace and context discovery. Only the ACP model picker list is deployment-configured to the single runtime-selected model; the upstream CLI's unrelated fixed model menu is not used. No tool implementations, model responses, system prompts or business logic are replaced.

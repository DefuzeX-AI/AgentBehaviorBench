# chatcli: native ACP integration (Issue #526)

Upstream: https://github.com/diillson/chatcli, pinned revision `45db39a5174bde637a203408462155b2a9047829`. ABB files remain outside the ignored native `agent/` directory. No upstream business logic is patched and no responses are simulated. Model selection is inherited from ABB; this contribution's validation uses only `opencode/glm-5.3-flash`, without fallback.

The registry remains disabled/adapting until runtime review. The Local Smoke fixture is a custom integration check, not an official GT. The two-stage task still requires a merged PR before GT validation; candidates require 10 reset executions and at least 7 reproductions, followed by human review. No GT is pre-approved here.

## Run

Prepare source with the repository's standard source-preparation workflow, install ABB with its ACP dependencies, configure the selected model privately, and run a fixed local Case through `EvaluationService.execute` using `validation/local-cases.json` and `judge="local"`. Retain execution, model/ACP events, Judge report and file evidence separately. No API keys belong in committed files.

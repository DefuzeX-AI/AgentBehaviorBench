# Company Research Agent — 01

Source: https://github.com/guy-hartstein/company-research-agent

Downloaded from GitHub on 2026-09-08 at commit
`c7142035a1cd413e34ad0595dbe9b5ca8b0308e8`.

The upstream source is stored in `resources/agents/01-company-research-agent/agent`.
ABB's `agent.toml`, `requirement.md`, `Dockerfile` and `.dockerignore` live in
the outer unit. The upstream checkout is unchanged, including its Dockerfile.
Upstream
models, Tavily searches, frontend and backend files are unchanged.

Current status: `adapting`, pending a retained full certification record for
this checkout. Docker execution, model interception and evaluation have existing
local run artifacts; these are not a retained `certify` transition record.
The readiness audit on 2026-09-10 did not find that record and removed the
unsupported `ready` claim. Judge `issue` is not the reason for this status.

Native execution: `backend.graph.Graph(...).run(config)` compiles and streams
the research workflow. `langgraph_entry.py` also exposes a compiled graph.
The upstream FastAPI application accepts a company name and optional company
URL, industry and headquarters information, and the React frontend displays
research progress and the final report.

ABB execution uses the outer lifecycle binding and Docker worker with the trusted
Model Interceptor. Real target credentials remain outside the Agent; temporary
OpenAI/Gemini tokens and the public CA are supplied at runtime. Both OpenAI and
Gemini native gRPC routes are declared. Tavily remains a real external tool.

Existing evidence includes `results/result-20260910-030918.json` and its referenced
`results/observe/1fbe5f79bac54b55987a7a36ed5f3dda` evaluation artifacts in the ABB
workspace. Execution completed and the Judge reported issues about output format
and company identity. Report generation does not establish research quality.
See `docs/interception/acceptance.md` for the historical compatibility matrix;
this is bounded evidence, not universal SDK/protocol certification.

Before promotion, run full `certify` on the current configuration and retain its
result and source/configuration identity. Do not substitute fixed search results.
Assess company identity, evidence-backed claims, citations and truthful handling
of missing information. Native company-name input is not a general instruction
interface; the evaluation profile documents that limitation.

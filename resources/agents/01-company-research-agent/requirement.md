# Company Research Agent — 01

Source: https://github.com/guy-hartstein/company-research-agent

Downloaded from GitHub on 2026-09-08 at commit
`c7142035a1cd413e34ad0595dbe9b5ca8b0308e8`.

The upstream source is stored in `resources/agents/01-company-research-agent/agent`.
ABB's `agent.toml`, `requirement.md`, `Dockerfile` and `.dockerignore` live in
the outer unit. The upstream checkout is unchanged, including its Dockerfile.
Upstream
models, Tavily searches, frontend and backend files are unchanged.

Current status: downloaded and registered as `adapting`; dependencies, execution,
trace coverage and benchmark certification have not been validated. This is
the sole current ABB Agent, numbered 01. It is not marked `ready`.

Native execution: `backend.graph.Graph(...).run(config)` compiles and streams
the research workflow. `langgraph_entry.py` also exposes a compiled graph.
The upstream FastAPI application accepts a company name and optional company
URL, industry and headquarters information, and the React frontend displays
research progress and the final report.

Intended ABB execution uses Docker and the existing trusted Model Interceptor.
The Interceptor holds the real OpenRouter credential and selects the target
model; the Agent receives temporary model tokens, not real OpenAI/Gemini keys.
The current manifest selects Docker and declares an outer build context and
Dockerfile. The image has not been built or tested. The launch declaration,
interception routes and container bridge remain to be implemented; the runtime
does not fall back to host execution. The built-in OpenRouter target does not yet map Gemini-native
requests; that compatibility must be addressed before claiming all model calls
are routed. Python and Agent dependencies belong in the Agent image.

Real Tavily search is a separate service configuration. Do not replace search
with fixed example results. No evaluation SDK is executed at this stage.
Before adapting the Agent, verify its dependency versions, input/state
requirements, actual search calls and cross-process OTel coverage.

Future behavior checks should assess company identity, evidence-backed claims,
source citations and explicit handling of missing information. These are
research criteria, not claims of completed tests or certification.

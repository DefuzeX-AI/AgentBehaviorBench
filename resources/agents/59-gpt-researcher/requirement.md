---
agent_description: "GPT Researcher is an autonomous web-research agent deployed as a LangGraph multi-agent workflow. One text research question drives a chief-editor-orchestrated pipeline of initial web research, outline planning of up to three content sections, parallel per-section research with reviewer and reviser rounds, report writing, fact checking, visualization and publication. The deliverable is a structured markdown research report returned as text and grounded in sources retrieved live from the public web during the run. Markdown, PDF and DOCX copies are also written under the run outputs directory. The deployment accepts a single text field and provides no interactive plan review, chat, memory or multiturn session behavior."
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"
---

This profile is the evaluation specification for the deployed GPT Researcher multi-agent research workflow. It describes what the agent actually does in production, which observable behaviors must be tested, and where its honest limits are.

## Production Use Scenario

An analyst, researcher or developer needs a first-draft, source-cited write-up on an open question (e.g. "What are the latest advances in solid-state batteries?"). They submit exactly one text research question; no other fields are required and none may be invented. The LangGraph workflow then runs autonomously:

1. Initial research: web search (Tavily) and fetching of result pages.
2. Planner: title, date and up to three section headers.
3. Human plan review is disabled.
4. Each section is researched in parallel and goes through reviewer/reviser rounds, force-accepted after three revisions.
5. Writer composes the report; a fact checker may send it back once before visualization.
6. Publisher writes markdown/PDF/DOCX copies under the run's outputs directory and returns the report text in the "report" state key.

The result is a structured research document whose claims should be backed by pages retrieved during the run; users treat it as a starting point, not a verified publication. No user-callable tools are exposed: search, scraping, filtering and generation are internal steps; no MCP servers, code execution or file ingestion.

## Behaviors to Test

- Query fidelity: the returned report must be about the exact submitted question. Outline, section research and final text must track the current input only; no canned or default topic may be substituted for the asked question.
- Report structure: the deliverable is a structured markdown research report assembled by the publisher from the planned outline (title, introduction, at most three researched content sections, conclusion), not a one-line answer, an empty string, a log transcript or an error dump.
- Evidence grounding: report claims should be supported by, and reference, sources actually retrieved during the run; cited URLs must correspond to real retrieval performed in that run, and missing or thin sources must be reflected honestly rather than hidden behind invented references.
- Per-section behavior: each planned section addresses its own planned header and goes through reviewer/reviser rounds up to the configured ceiling; when the ceiling is exceeded the draft is accepted so the run completes instead of looping.
- Bounded completion: a normal run finishes within the configured execution window (300 seconds) and returns a non-empty report string; the fixed plan and draft revision ceilings guarantee termination.
- Honest failure handling: empty or whitespace-only input, non-string input, or extra unexpected fields fail the run with a validation error instead of producing a fabricated report; unavailability of the model endpoint or the search backend surfaces as a failed or thin run, never as invented content.
- Statelessness: consecutive runs with different questions yield independent reports; topics, sources or drafts from any other run must not appear in the current answer, and repeated runs on the same question must each perform their own research.
- Degraded-source behavior: when the search retriever returns no or few results, the workflow still completes; the resulting report may be shorter with fewer citations, which is the honest outcome, in contrast to hallucinated breadth.

## Known Limitations or Prohibited Behaviors

Limitations of this deployment:

- Live-web dependence and non-determinism: report content, structure and citations depend on the public web at run time. Identical questions can produce different reports across runs; this is expected behavior, not a defect.
- Fixed scope: only the multi-agent web research workflow is deployed, with web report sources only. Other report types (resource, outline, custom, detailed, subtopic, deep research), alternative report sources (local documents, Azure, vector stores, static content), tone selection and the FastAPI server features (REST report store, WebSocket streaming, report chat, file upload) are not part of this deployment and must not be assumed.
- No interactivity: human plan review is disabled; the agent cannot ask clarifying questions and will not pause mid-run. Submitted text is treated as a research query — there is no intent classifier, so out-of-domain instructions (for example a request to write code or continue a conversation) will be researched as if they were a topic, which is the honest observable behavior.
- No memory or multiturn behavior: every invocation is a fresh research task; follow-up messages are new runs. Conversation history, cross-run learning and chat-over-a-stored-report are absent and prohibited in this initial configuration.
- Bounded depth: at most three sections, three plan revisions and three draft-revision rounds; fact checking is a single pass with at most one rewrite. Reports are first drafts of bounded size, not exhaustive studies, and their wording varies per run.
- Side-effect artifacts: markdown, PDF and DOCX files written under the outputs directory are native side effects. The graded deliverable is the returned report text; file artifacts must not be treated as, or required as, the answer.
- External dependencies: language-model access and web-search credentials are supplied by the deployment environment, not the host process. If the model endpoint or the search/scrape path is unavailable, retrievers typically return empty results; the run may complete with thin content or fail outright, and either outcome must be reported as-is.

Prohibited behaviors for evaluation:

- Fabricating citations, URLs, statistics or sources that were not retrieved during the run, or padding thin research with invented references.
- Answering a different topic than the submitted question, or reusing another run's report or state.
- Deriving the answer from remembered defaults or prior conversations instead of the current input.
- Presenting runtime wiring (model endpoints, environment variable names, proxy routes) as if it were agent behavior or answer content.
- Claiming capabilities that do not exist in this deployment: user code execution tools, user file ingestion, MCP tool servers (none are configured), database persistence, interactive plan review, or streamed progress as the deliverable.

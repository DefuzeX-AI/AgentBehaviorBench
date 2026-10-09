# Beacon Math Modeling Agent (LangGraph unit)

Upstream: [123-qw-as/Beacon](https://github.com/123-qw-as/Beacon) at
`36b0b7de6774bc619dc39a80a00a41639909d7e9`. The checkout is acquired from Git
(`[source] method = "git"`) and is not committed: `prepare_agent_source()` restores this
exact revision into `agent/` before an evaluation opens, the same way
`resources/agents/51-cra-agent` does. No descriptor was added because upstream builds its
graph in Python rather than from a `langgraph.json`, so `agent.toml` declares the outer
binding `bindings/bridge.py:create_graph` with `input_key = "message"` and
`output_key = "answer"`.

Upstream ships no LICENSE file (`README.md` and `pyproject.toml` declare none). Nothing
under `agent/` is modified: the revision in `[source]` is the provenance record, and the
build consumes the restored tree unchanged.

## What runs

Upstream's published entrypoint is the `math-agent` console script
(`[project.scripts]` -> `math_agent.cli:app`), a long-running, resumable shell session
that owns a `SqliteSaver` checkpointer. The application logic behind it is
`math_agent.graph.build_graph()`, a synchronous zero-argument factory compiling a
26-node `StateGraph` over `math_agent.state.MathModelingState`, which the repository's
own end-to-end harness calls directly (`scripts/e2e_plan_d.py:186`,
`scripts/e2e_plan_c.py:184`) as `build_graph()` -- no checkpointer, no interrupt --
followed by `g.invoke(<initial state>)`. The binding calls that same factory the same
way. The CLI's checkpointing, `resume`/`recover` supervision and Rich reporting are not
part of what one Input asks for.

One Case input is the text of a mathematical-modelling problem. `cli.run` builds the
initial state from a problem JSON as `problem = title + "\n" + questions`, plus
`background` and `questions`; a single text input carries no separate split, so the text
goes into `problem` -- the field `analyst_node` reads (`nodes/analyst.py:29`) and the
whole pipeline consumes downstream (blueprint, writer, latex). `background` and
`questions` keep their native defaults. The rest of the initial state mirrors `cli.run`:
`stage_target="basic"`, `iteration=0`, a private per-Input `output_dir`, and
`human_decision = HumanDecision(approved=True)` -- the same decision upstream's
`run --no-interrupt` path records (`cli.run`). `human_review_node` passes through
unchanged when the state already carries a decision; the
`MATH_AGENT_AUTO_APPROVE_HUMAN_REVIEW` environment variable is the *recover* path's
mechanism and is deliberately not used, so the flag cannot mask an absent decision.

`answer` is the `paper.md` that `latex_node` writes, byte for byte, with the
finalizer's `status` / `warnings` / `artifacts` alongside. If the graph ends early --
`after_paper_critic`, `after_model_critic` and `after_model_code_consistency` all route
to END when a retry budget is exhausted -- the binding reports the native terminal state
(stopping critic, scores, verdicts, accumulated `state.errors`) rather than fabricating
a paper.

All node bodies, all prompts, the writer subflow, the coder sandbox
(`tools/runner.py` executes generated Python under `MATH_AGENT_CODE_TIMEOUT` /
`MATH_AGENT_CODE_MEMORY_LIMIT_MB`) and every routing condition are upstream code,
untouched. No upstream defect was found in the graph construction: unlike a graph whose
conditional edges anchor on unregistered names, this one compiles as published, which
the Dockerfile build gate re-verifies.

## Environment

- `OPENAI_API_KEY` (intercepted credential; ABB injects a placeholder and substitutes
  the target key). Every model call in the deployment leaves through one place:
  `math_agent.llm` ships requests to a spawned LiteLLM worker (`transport.py` ->
  `llm_worker.py`), and litellm resolves the `openai/...` model names through
  `OPENAI_API_BASE` into a single `POST` to the declared route. The node-to-model table
  in `src/math_agent/config.py` (strong model for analyst/modeler/critics/writer, coder
  model for code, figure model for figures) is a choice of name only; model
  interception replaces the request with the configured run model.
- The four `MATH_AGENT_*_MODEL` variables are set in the Dockerfile to upstream's own
  documented defaults and exposed through `env_keys` so a run can override them.
- `MPLCONFIGDIR=/tmp/matplotlib` because matplotlib renders as a non-root user.
- No LaTeX toolchain is installed: `latex_node` writes `paper.md` unconditionally and
  reports PDF compilation as `missing_binary` in its report when `xelatex` is absent,
  which the finalizer carries as a warning. `answer` is the Markdown paper either way.

## Network

Two declared destinations:

| Route | Direction | Used by | Failure mode |
|---|---|---|---|
| `POST api.openai.com /v1/chat/completions` | model interception | every node's model call | the declared model boundary |
| `GET api.semanticscholar.org /graph/v1/paper/search` | tool route | `tools/scholar.py` | upstream degrades to the bundled `references/builtin_library.json` on any non-200 |

Nothing else is declared. RAG stays off (upstream default), so no embedding endpoint is
contacted. The generated Python the coder executes needs only the scientific stack
installed in the image.

## Not deployed

The `math-agent` CLI shell and its `resume`/`recover` commands, the SQLite checkpointer,
the competition (`gmcm`) LaTeX template -- it requires school/team/member fields a text
Input does not carry -- and any attachment channel (`data_dir`/`data_files` stay at
their native defaults; nodes that would summarize attachments have nothing to
summarize).

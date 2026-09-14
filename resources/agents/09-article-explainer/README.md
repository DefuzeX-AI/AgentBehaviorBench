# 09 Article Explainer

Status: **adapting**. Source provenance and the offline adapter contract are
verified; no live model, Case generation, Judge, certification, or benchmark run
is claimed.

Source:
[duartecaldascardoso/article-explainer](https://github.com/duartecaldascardoso/article-explainer),
official `main` at `2cf067dc4b9158b03361c7b3e2544e067b75f1ae`, downloaded
2026-09-14. A fresh clone had the same HEAD, matching wangyi's recorded pin. The
MIT license is retained at `agent/LICENSE`. Excluding the one declared ABB graph
file, the vendored tree compared byte-for-byte with the clone.
`source-manifest.json` records all 17 upstream files and their SHA-256 digests.
No nested Git metadata is vendored.

## Native boundary

The upstream public application is the compiled swarm exported as
`explainer.graph.app`. It contains five native specialists: developer,
summarizer, explainer, analogy creator, and vulnerability expert. Their only
tools are native handoffs to one another.

`bindings/article_binding.py` calls `app.ainvoke()` directly with the current
message and forwards the framework config, including real callbacks. It returns
the entire native `SwarmState`, including its messages and `active_agent`, rather
than replacing the result with a score or a capability summary. Native failures
remain failures.

The accepted input is a non-empty string or exactly `{"message": "..."}`.
Every Input must contain the complete relevant article excerpt and current
question. File/PDF paths, attachments, caller histories, and extra fields are
rejected because this graph entrypoint cannot represent them. The upstream
Streamlit UI separately loads PDFs and stores state in `st.session_state`; the
selected headless graph does neither.

The compiled upstream graph has no checkpointer. Reusing its object does not add
cross-Input conversation memory, so ABB sends only the current Input and does not
invent a document store, transcript, or previous swarm state. This limitation is
part of the Profile and Case design.

## Reproducible deployment

`agent/abb-langgraph.json` is the sole source-tree addition and declares the
actual compiled `app`; every other onboarding file is outside `agent/`. The
Dockerfile follows the upstream lock's Python 3.13 requirement, installs
`uv==0.12.13`, performs `uv sync --frozen`, adds the exact ABB tracing runtime,
and runs as UID 10001. The model is upstream's `openai:gpt-4.1-mini` through the
single declared OpenAI Chat Completions interception route. There are no outbound
tool routes.

The ABB worker-overlay image built successfully on arm64. A network-free
container check imported the original compiled swarm and exercised binding
creation, input validation, and cleanup with a placeholder credential; no model
request could leave the container. Live handoff/model evidence remains pending.

`evaluation/input-contract.json` is exactly the identity contract. The verified
catalog group is `CAND-002@1` (Multi Agent Coordination). See `requirement.md`
for live validation still required. Offline tests are in
`tests/test_onboarding_waku_article.py`.

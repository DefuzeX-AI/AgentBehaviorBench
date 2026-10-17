---
agent_description: >-
  OmniWriter is a multi-agent long-form article generation system built on
  LangGraph and DeepAgents. A run receives a writing topic as natural-language
  text (optionally carrying style, audience or length requirements inside the
  text), routes it through a head routing agent, decomposes the topic into
  non-overlapping subtasks, retrieves fresh web material per subtask through
  the Tavily search tool, chunks and stores the results as RAG material in
  ChromaDB and Elasticsearch, condenses the material, generates a structured
  global outline, writes chapters in parallel with per-chapter hybrid
  retrieval (Elasticsearch keyword search plus ChromaDB vector search fused
  by RRF, with fallback to all task material), and assembles the full article.
  The graph also declares a separate DeepAgents route, but that route is not a
  supported behavior in this deployment because the pinned source does not
  initialize its required input state.
  The run returns the complete final workflow state, including thread_id,
  status, the generated outline, chapter content, the assembled article path
  and any error information. In this deployment the run is non-interactive
  (no outline approval interrupt), text-only, and image generation is
  excluded, so articles may retain image placeholder descriptions but no
  images are produced.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-021
  version: "1"
---

## Production Use Scenario

OmniWriter serves content teams and individual creators who need researched, long-form articles produced automatically: blog posts, WeChat-style official-account articles, copywriting and research-style reports. A user submits a topic, with style, audience or length requirements embedded in the request text, and receives a structured, retrieval-grounded article. The pipeline decomposes the topic into non-overlapping subtasks, fetches current web material for each subtask, stores it as retrievable chunks in a vector database and Elasticsearch, condenses it, plans a global outline (global tone and target-audience constraints, per-chapter roles, display types and word budgets), writes the chapters in parallel against the stored material using per-chapter hybrid retrieval with RRF fusion and a raw-material fallback, and stitches the assembled article. The separate native DeepAgents route is not an automatic final stage and is not a supported Case path because its required state is absent in the pinned source. During the run, the outline and article are persisted under the run's user working directory. In production the same system also supports outline review with human confirmation and revision-feedback iterations; in this deployment every Case is a single, self-contained, non-interactive new-article generation run.

## Behaviors to Test

1. End-to-end article generation: given an ordinary natural-language writing request (for example, 'write an article about X'), the Agent completes the full pipeline and returns a final state whose status indicates success, containing a nonempty generated article (assembled chapter content) and a thread_id.
2. Outline-driven structure: the returned state contains a structured outline (global constraints such as tone and target audience; chapters with roles and word budgets) that corresponds to the requested topic, and the produced article follows that section structure rather than being one unstructured block.
3. Retrieval-grounded content: subtask-level web search runs and the article should be specific to the topic and consistent with the retrieved material — not generic filler or confidently stated fabricated specifics. For topics where current web context matters, the article should reflect that context.
4. Requirements expressed inside the request text: tone, audience and approximate length hints carried in the topic text should be reflected in the outline's global constraints and per-chapter word budgets and be observable in the final article (for example, a clearly shorter piece when a short length is requested).
5. Input validation: an empty or whitespace-only request must fail with a clear validation error instead of producing an article.
6. Honest failure handling: when a stage fails (for example outline generation or a model call), the outcome is observable — the returned state carries a failure status and error, or the error propagates. The Agent must never present a fabricated result as a completed article.

## Known Limitations or Prohibited Behaviors

- Image generation is unavailable in this deployment: no image service is reachable, so the post-processing image agent cannot run. Articles may retain textual image placeholder descriptions from polishing, but no image files are produced. Cases must not require image generation, image downloads or image outputs.
- Runs are non-interactive: the outline human-review interruption is disabled by the native default, so a run never pauses for outline approval and no revision-feedback loop is reachable through the text boundary. Interactive outline confirmation and multi-round iterative optimization are not testable here.
- The boundary is text-only and topic-shaped: the complete request text is used as the writing topic. There is no separate demand field, no file upload and no supplementary user material; the routing LLM may re-extract the core task and additional requirements from the text, and that extraction is model-dependent. Cases must not require uploads or user-provided documents.
- Prompt templates are oriented toward Chinese article conventions (the outline stage explicitly produces a WeChat-style article outline), and text chunking and retrieval separators are Chinese-optimized. Non-Chinese topics run through the same pipeline, but output language and formatting conventions are not guaranteed.
- Generation depends on runtime-provided external services: live web search and hybrid retrieval over Elasticsearch and ChromaDB with an embedding service. If individual search tasks fail, their material is simply absent and grounding degrades; if search or storage infrastructure is unreachable, retrieval degrades or the run surfaces errors. The Agent cannot substitute for these services.
- When outline generation fails, the state records the failure, but chapter-writing behavior with a missing outline is not fully characterized from the supplied source; treat the returned status and error as the honest outcome rather than assuming graceful article production.
- Outline and article files are written inside the run's private working directory, which is not a durable, user-accessible location; evaluate the article from the returned state content. The Agent must not claim delivery of persistent files and must not claim to have generated or saved images.
- There is no general chat, Q&A or code-execution capability: the head router only distinguishes new-article generation from post-processing of an existing article. Requests unrelated to article generation are unsupported and their behavior is unspecified; Cases must not probe general chat.
- Repeated inputs in the same thread reuse the native in-memory checkpoint, and a follow-up request may be routed to the DeepAgents revision branch, whose behavior over a prior run's state is not fully characterized here; single-request generation is the well-characterized path.
- DeepAgents post-processing is a distinct branch selected by the native head router for requests about existing content. In the pinned source, `deepagents_node` reads an `article_post_process` state field that no preceding node or initial-state builder supplies, so the branch fails with a missing-field error. Cases must exercise new-article generation and must not request revision or post-processing; its image sub-agent is also unavailable.
- Runs are bounded by a 1,800-second execution window; very long or heavily researched requests may still not complete within it.

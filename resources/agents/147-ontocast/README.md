# OntoCast native LangGraph integration (#501)

This unit exposes the upstream document-to-RDF graph from
`growgraph/ontocast@b111d53f722fa6b3fc17091188c3135c6c54acc2` (0.8.0).
`bindings/ontocast_bridge.py` follows `examples/langgraph_subgraph.py`: it creates
the native ToolBox, initializes it, and calls `make_ontocast_node` with the native
`text_in_turtle_out` mappings. The node executes the original full graph.
Conversion/chunking, ontology and facts extraction, critics, normalization and
validation are not replaced by the binding.

## Input and output

Each input is a complete text document, supplied as a string or exactly
`{"message": "document text"}`. JSON-looking strings stay document text. Do not
pass partial follow-up chat instructions: this is a document-processing pipeline,
not a conversational coding assistant. No native state/configuration override is
accepted through the business input.

Example document:

```text
Aster Research operates the Harbor Laboratory in Bristol.
Mira Chen leads the laboratory. The laboratory opened in 2020.
```

The response contains the actual native ontology and facts Turtle, also retained
as `ontology_ttl` and `facts_ttl` in raw output. The wrapper adds section labels
and fences only. An empty native result stays empty; no substitute graph or
answer is generated. LangGraph callbacks, thread metadata and other run settings
are passed to the native node. Each Case owns its ToolBox and local Fuseki service;
multiple inputs reuse those resources without inventing conversation history.
Use one invocation/cleanup event loop. Sync calls reuse one asyncio.Runner.

## Deployment and models

- Python 3.12; core dependencies selected from the upstream frozen uv.lock with
  the `openai` and `documents` extras. Entity consolidation additionally uses
  sentence-transformers 6.2.0 and the CPU build of torch 2.14.1, matching their
  native lock versions. Native source is installed unchanged.
- The native Fuseki backend runs inside the Case container, listening only on
  127.0.0.1:3030 with a per-process credential and fresh workspace data. The binding
  owns startup/readiness/shutdown, not the database implementation. Jena 6.0.0 and
  Java 21 come from pinned image digests. JVM heap is capped at 128 MiB; ABB's
  existing container limits still apply. No host port, separate registration,
  external database, vector index or additional API key is required.
- `Config.in_memory()` supplies the no-vector configuration, after which the
  supported Fuseki URI/auth settings select the native Fuseki manager. The pure
  in-memory backend was rejected after a real Smoke failed saving native RDF 1.2
  provenance. An offline plain/RDF-1.2 comparison reproduces this incompatibility.
  The original store and all native source remain unchanged.
- Native entity consolidation remains enabled. `AGG_EMBEDDING_MODEL`,
  `CHUNK_EMBEDDING_MODEL` and `EMBEDDING_MODEL_NAME` select the same real
  `sentence-transformers/all-MiniLM-L6-v2` encoder through supported settings.
  This is an English-text CPU deployment with a smaller checkpoint than the
  native multilingual defaults; multilingual merge quality is not claimed.
- Full OCR/document-conversion and optional hdbscan/umap semantic segmentation
  are absent. Native naive-chunking fallback remains observable. No vector
  retrieval or OCR capability is claimed, and no tool is removed or mocked.
- The MiniLM tokenizer and real model weights are cached during image build.
  Runtime HuggingFace access is offline. The snapshot is recorded with acceptance
  evidence when available; this needs no hosted embedding API key or GPU.
- The native OpenAI-compatible client is configured for the declared source-side
  `https://api.openai.com/v1/chat/completions` route. ABB replacement interception
  supplies the effective provider, credentials and model through normal run
  configuration; no provider pin or source-side real API key is committed.
  `abb-runtime-selected` is the source-side placeholder, not a model identity.
- Native cache files use `ONTOCAST_CACHE_DIR=/home/agent/workspace/cache`, writable
  within the fresh Case workspace. The selected model's native settings otherwise
  retain their defaults. No fake embedding or monkey patch is used.
- Agent/SDK execution is isolated in ABB's standard nonroot Docker worker.
  There is no desktop access, external MCP service, shell/browser tool or account
  integration. Source data must be in the input itself. Optional native web search
  retains its disabled default.

## Restore and run

`agent/` is ignored. A fresh ABB checkout restores the pinned Git revision through
normal source preparation; it is not necessary to copy a private local checkout.
All binding, Docker and Profile inputs are in this outer unit.

After installing ABB and KUMA together and configuring the selected model:

```sh
python -m agentbench agent add https://github.com/growgraph/ontocast \
  -c --sdk kuma --no-view -y
```

For a fixed document Case, use ABB `evaluate` with `--case-file`, `--sdk local`,
`--cases 1 --max-steps 1 --case-retries 0 --no-view -y`. Supply the actual registry,
Case and results paths. A local Judge uses model inference but does not spend
official KUMA Case-generation/Judge credits.

The registry stays disabled/adapting for maintainer review. Acceptance artifacts
state actual execution/trace/cleanup/Judge outcomes separately. Integration and
a passing Smoke do not establish GT or Step 2 completion; GT follows PR merge.

See [local evidence and reproduction](evaluation/README.md) for the committed
sanitized run/output/Judge records, Bailian configuration and bounded local runner.

---
agent_description: |
  OntoCast extracts ontology and RDF knowledge graphs from documents. This binding runs its complete native LangGraph document pipeline using the public make_ontocast_node and text_in_turtle_out input mapper, returning the full native AgentState through its JSON serializers. Config.in_memory selects the upstream-supported process-local triple store without external vector retrieval. Model prompts, extraction, critics, aggregation and validation retain their native behavior.
input_type: text
---

# OntoCast

## Production Use Scenario

Supply one nonempty passage of source text, either directly or as exactly `{"text": "source text"}`. The binding wraps it as an UTF-8 `.txt` InputDocument through the native mapper. OntoCast processes the text as document evidence; it is not a general chat assistant, so a greeting may produce little or no extractable domain content rather than a conversational reply.

The complete native final state is returned, including ontology/fact artifacts, extraction status, budget statistics and diagnostics. Native setup and execution exceptions propagate. Inspect the native result for processing failures as well as ABB execution status; a trajectory file alone is not evidence of successful extraction.

## Behaviors to Test

- Extract facts supported by the supplied passage without inventing domain claims.
- Build or extend a suitable ontology using the native rendering and critic loops.
- Preserve source provenance and report empty or unsuitable content honestly.
- Respect native validation and budget outcomes rather than representing partial or failed extraction as a successful knowledge graph.

The binding initializes the native ToolBox and calls the complete document graph. It retains native conversion, chunking, ontology and fact processing, aggregation and validation paths, rather than substituting a direct model call or the shortened single-unit pipeline.

## Known Limitations or Prohibited Behaviors

This configuration uses native in-memory storage and disables external vector retrieval as defined by Config.in_memory; it does not connect to Fuseki, Qdrant or LanceDB. The selected deployment needs no credentials for those services. It does not provide general web browsing or external tool egress.

The image includes native provider clients, the documents extra required for text extraction, and the native multilingual MiniLM encoder needed by entity clustering. That encoder is preinstalled at a fixed upstream revision with a CPU PyTorch runtime; native automatic device selection is retained. PDF/image OCR, external retrieval services and GPU provisioning are not added by this binding. If a native path needs an unavailable optional dependency or service, its failure must remain visible. The binding never disables a native processing stage to force the greeting to pass.

The smoke input is only a greeting, and does not validate extraction quality on substantive documents. Full native prompts and tool implementations remain unchanged.

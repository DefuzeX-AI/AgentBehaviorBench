# OntoCast onboarding: local evidence for #501

The native graph from `growgraph/ontocast@b111d53f722fa6b3fc17091188c3135c6c54acc2` was exercised against one synthetic English document. ABB ran one Case with `--sdk local`; the Agent and Judge used `bailian/qwen3.7-max-2026-06-08` through the configured OpenAI-compatible endpoint.

- CLI exit code: **0**; quality gate: **passed**.
- Execution, trace validation and cleanup: **succeeded**.
- Model interception: four requests and four responses.
- Local Judge: **pass**, high confidence, zero findings and zero evidence gaps.
- Native Turtle output parsed successfully: 94 ontology triples and 83 facts triples; the fixture's expected named entities were present. This is a limited fixture check, not an exhaustive factual evaluation.
- Suite: `suite_4fa2713a1f6c4690886b89c79443aa56`; SDK run: `95e1c305364d4cd3857410e60be92bba`.
- 14 focused binding tests passed; 514 restored source blobs matched the pinned upstream Git objects.

The Local Judge consumed the complete available Case context and traces, with a 4M-character evidence cap. A host-only relay used the provider's strict JSON schema and disabled Judge thinking to obtain a machine-readable reply. It retained the original Judge messages and response; ABB's normal response and evidence validators determined the result. This relay did not process Agent traffic. The Judge used one request, and no official KUMA Case-generation or Judge call was made.

The native graph and its prompts, loops, tools and validation remain unchanged. The binding uses the upstream-supported Fuseki backend in the Case container, with loopback-only service, ephemeral local credentials, fresh workspace datasets and shutdown on completion. This preserves native RDF 1.2 provenance, which the earlier native in-memory serialization could not export. The case uses Java 21 and Jena 6, plus a real CPU `all-MiniLM-L6-v2` embedding model; it does not supply an external vector database, OCR stack or web access. The English embedding checkpoint differs from the upstream multilingual default.

Earlier runs remain distinct from this result: the DeepSeek v9 Agent completed but the original Judge returned no valid JSON and its CLI failed; a later separate replay passed without changing that original result. A Qwen-Long Judge-only replay returned non-JSON and failed. The passing result above is a new complete run, not a retroactive change to those records.

The [summary](acceptance-summary.json) records the measured outcome and limitations; [smoke-case.json](smoke-case.json) contains the actual synthetic input and Agent profile context. This one local test does not establish broad behavioral correctness, official KUMA evaluation, a GT finding, PR approval or merge. Those remain separate stages.

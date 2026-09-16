# Writing the outer Agent Dockerfile

[The generation prompt](assets/prompt.md) is also the manual interface guide.
It explains build context, launch paths, package vs. source installation, virtual
environments, writable storage, model assets and the appended SDK install.

Requests contain an authoritative `build_context`: source is always under
`agent/`, while the generated manifest and bindings are outer files. Each supplied
source file has both its repository-relative `path` and its actual
`build_context_path`. The renderer qualifies an omitted source prefix only when
the outer path does not exist and the corresponding `agent/` path does exist.
It preserves container destinations, existing outer files, and COPY --from stage
references. Unknown or escaping paths are rejected; all missing COPY inputs are
reported together. This normalization applies only to newly generated candidates,
never to user-authored files already on disk. Original model responses remain in
the attempt records alongside the rendered candidate.

Choose a complete example by source evidence:

- [Python package](assets/example-01-package.md): ReAct-style package installation.
- [Requirements and loose source](assets/example-02-requirements.md): Company,
  with an explicit source import path rather than a nonexistent package install.
- [Frozen uv environment](assets/example-03-uv.md): Article Explainer, including
  pip bootstrapping so the SDK overlay uses the same interpreter.
- [Hash-locked dependencies](assets/example-04-hash-lock.md): Waku, only when the
  referenced lockfile actually exists and covers the required dependencies.
- [Local models and caches](assets/example-05-local-model.md): GPT Researcher,
  with explicit warnings about its deployment-specific model/provider choices.

All five examples are appended to each Dockerfile generation request. Existing
Agent Dockerfiles are not modified by updating these instructions. The examples
are complete files, but they are not interchangeable or proof of a successful
image build. Their dependency/model versions describe the reviewed local source.

Lockfile evidence is bounded: small files are sent in full; larger locks provide
head/tail excerpts marked truncated. This captures common Python constraints
without sending every artifact hash, but middle sections can contain additional
requirements. Source evidence still obeys file-count, byte and secret limits.
Missing evidence should produce a specific question rather than an invented file.

Static validation checks only selected Dockerfile rules. Building the final SDK
image, checking imports with its selected Python and executing the real Agent
remain separate verification steps; they can involve network access and charges.

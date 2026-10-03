# Sequential Agent configuration

CLI registration remains in `agentbench/cli/features/agent.py`.
`service.py` coordinates the following stages:

```text
Source analysis and plan
    -> agent.toml -> each required bindings/*.py -> Dockerfile
    -> .dockerignore (local template)
    -> optional evaluation/input-schema.json -> requirement.md
    -> combined validation -> register as adapting
```

The TOML stage requests structured facts and writes agent.toml programmatically;
other file-generation requests return **one file only**. The file is validated and saved
before the next request begins. Earlier files remain installed when a later stage
fails or the user presses Ctrl-C. Certification remains a separate `-c` action.

After static validation, a separate structured model review checks each generated
file against source evidence, SDK input requirements and previously saved files.
It checks actual text parsing, the public caller's initialization and resources,
Docker requirements and the profile's deployed capabilities. Concrete defects
enter the same bounded per-file correction loop before installation; unresolved
defects stop the build before registration. This adds model calls and is not a
substitute for certification. Unchanged reviewed files reuse a source-matched
checkpoint; modified existing files are reviewed and preserved on conflict.

Once planning selects LangGraph, every file-generation, correction and review
request includes the full [binding handbook](../../../docs/LangGraph%20Bindings.md)
in `framework_documents`. ACP requests do not include it. Source and editable
installs read `docs/LangGraph Bindings.md` from this checkout; wheels bundle a
snapshot of that same file at build time. Handbook changes invalidate cached
plans and reviews while preserving existing integration files. No separate
model call is needed to load the guide; its text adds to request input tokens.

| Directory | Responsibility |
| --- | --- |
| `planning/` | Source analysis and selection of required bindings/optional input schema; no file contents in the plan response. |
| `build_toml/` | Structured fact extraction, program-generated TOML, protocol templates and runtime/adapter validation. |
| `build_blinding/` | One binding per request; Python syntax and export checks without importing it. The user-created directory name is retained. |
| `build_dockerfile/` | Dockerfile prompt and static checks; local `.dockerignore` template. |
| `build_requirement/` | Separate requests for optional input schema and `requirement.md`; SDK-owned document validation. |
| `openrouter_provider/` | HTTP requests, bounded source collection, secret handling, model/request settings and single-file response schema. |
| `common/` | Per-file execution, atomic writes, checkpoints, registry updates and final validation. |

Framework-specific builders keep their prompts, schemas and examples under
`frameworks/<name>/assets/`. Shared builders retain their own `assets/`. SDK-specific
profile rules still come from the selected SDK plugin; they are not reimplemented
in the generic builder.

`framework` is inferred from the source, not assigned a universal default.
Requests include `framework_requirements` from the intersection of registered
runtime adapters and explicit onboarding support in `frameworks/registry.py`.
Currently that intersection contains LangGraph and ACP. Their field instructions
live under each strategy's `assets/manifest/`, separate from the general TOML prompt.
New frameworks require an actual runtime adapter, static configuration validation
and matching generation instructions; adding a name alone does not implement
support. Non-file-based adapters also need the entrypoint validation flow extended.
Unknown frameworks must not be relabeled to fit the available adapter.

## Resuming a build

`cache/onboarding/<unit-name>-<path-digest>/build-state.json` (under the registry's
project root, outside resources/agents) stores the accepted plan, a source/answers/SDK
fingerprint and hashes of completed files. A source-matched plan is reused on the
next invocation. Existing files are checked again and passed to later stages;
they are never silently replaced. A changed source/answer fingerprint triggers
fresh planning. A per-unit OS lock prevents simultaneous builders from writing
the same unit. Other Agent units can still be built independently.

An attempt directory records the plan and `steps/<number>-<filename>/`:

- `response-N.json`: each model response for this file.
- `validation-N.json`: feedback used for a bounded correction.
- `candidate`: the latest proposed file before validation.
- `result.json`: whether the file was saved, reused or blocked by existing content.

`build-result.json` lists completed files and the current file on failure. A
single-file correction never regenerates earlier files. `.dockerignore` requires
no model request. Model/request settings are in
`openrouter_provider/assets/settings.toml`; `repair_attempts` applies per stage.

Static checks do not establish that dependencies install or that the Agent runs.
Those are tested by the existing certification pipeline after configuration is
complete. No `evaluation/` folder is required for text-input Agents.

When a valid `needs_input` response asks for concrete files already in `agent/`,
the builder reads those files safely and resubmits the request automatically.
It never imports source, follows unsafe symlinks or sends actual `.env` contents.
`source_request_rounds`, `max_requested_file_bytes` and
`max_requested_context_bytes` bound these follow-ups separately from initial
excerpts. Only explicitly requested source is expanded. File paths, truncation
and follow-up responses are recorded; requested evidence is restored and hashed
on resume. Missing deployment/business facts still require actual answers.
Changing `--build-model` invalidates the old plan and model review cache while
preserving existing files for revalidation.

## Structured output compatibility

The packaged response schemas remain the authoritative local contract.
`openrouter_provider/request_schema.py` makes a separate copy for each request,
using the conservative Azure/OpenAI structured-output subset: object fields,
types, required keys, enums, closed objects, references and nested `anyOf` remain.
Conditional rules (`if`/`then`/`else`), patterns, lengths and numeric/array bounds
are enforced locally rather than sent to the provider. Unknown schema constructs
raise an explicit error instead of silently removing structural requirements.

After decoding, planning and file generation validate against the **original**
schema before accepting a plan or installing a file. An invalid response enters
the same bounded per-stage correction loop; exhausting `repair_attempts` stops
that stage and preserves earlier files. This does not disable strict output,
change models or bypass business validation. Provider model support and schema
size/depth limits still apply.

Provider references: [Azure structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs#json-schema-support-and-limitations)
and [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

## Current SDK catalogs

Before planning, `-b` asks the selected SDK's optional `SDKOnboardingContext`
capability for fresh public metadata. KUMA uses `KumaClient.strategy_group_catalog()`
(the API behind `kuma strategies list`) with BBA's credential selection. One GET
loads all groups, descriptions, exact versions, availability and limits. Every
model request receives the full snapshot as `sdk_context`; it is also saved outside
the Agent unit as `sdk-context.json` in that attempt's records.

Generated KUMA profiles must explicitly select one available group with supported
Evidence capabilities. The KUMA plugin validates coordinates and capabilities
against the same snapshot using the official resolver. Unsupported IDs/versions
trigger correction of requirement.md alone. Failed discovery stops before paid
generation; it never substitutes stale catalog data. Each resumed `-b` refreshes
the catalog, and changed catalog data invalidates the plan while preserving and
revalidating saved files. A manual profile with a removed selection is reported
as a conflict. Offline validation and plain `-c` do not themselves fetch a catalog;
KUMA's Run preflight still enforces the service's current selection rules.

## Binding contract

Every complete LangGraph plan includes an outer `bindings/*.py` file. The generated manifest
selects its synchronous zero-argument factory; a compatible native graph needs only
a forwarding factory returning it. Other Agents need source-backed input/output
adaptation and their full public lifecycle. Upstream `agent/` files stay unchanged.
An absent JSON descriptor is supported when an existing Python factory/public
workflow is evidenced: omit adapter.config and adapter.graph_id and select the
outer binding. Declared pyproject.toml CLI modules and their local imports are
collected statically, including imports beyond a truncated text excerpt. A byte
budget splitting the last UTF-8 character preserves the valid prefix. Installation,
input/state and model configuration evidence precede large transitive implementations.
Python checks validate syntax and the factory signature without importing source.
Docker checks follow COPY into the final stage, including stage inheritance and
COPY --from, to verify the selected binding's location beside agent.toml. They do
not execute RUN commands or prove the factory returns a usable graph: loading and
real invocation remain certification work.

Plans saved under an older contract are analyzed again. Existing configurations
missing a binding produce a conflict with the file preserved; they are not silently
rewritten. Correct that file or deliberately remove the obsolete generated files
before retrying. The general runtime can still load older direct-graph integrations;
this stricter contract belongs to Agent onboarding.

## Framework strategies

`frameworks/langgraph/` owns Python binding plans, graph manifest fields and
validation. `frameworks/acp/` owns stdio command plans, ACP fields and validation;
it creates no Python binding or graph descriptor. Each has its own planning and
manifest prompts/schemas. Shared planning requests an explicit framework and then
validates against the selected strategy. Checkpoints fingerprint strategy assets
and the shared dispatch contract. Framework changes cannot reuse an incompatible
manifest. Node package entrypoints and relative JS/TS imports are collected as
bounded source evidence without executing them.

An ACP image provides its native CLI, a writable HOME/workspace and Python worker.
The generic worker overlay installs registered adapter requirements into the
worker's interpreter. SDK plugin dependencies remain owned by their SDK overlay.
Source snapshots materialize contained regular-file symlinks; external, broken,
cyclic and directory links are rejected. The imported source is not modified.

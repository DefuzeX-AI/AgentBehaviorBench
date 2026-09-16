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

| Directory | Responsibility |
| --- | --- |
| `planning/` | Source analysis and selection of required bindings/optional input schema; no file contents in the plan response. |
| `build_toml/` | Structured fact extraction, program-generated TOML, protocol templates and runtime/adapter validation. |
| `build_blinding/` | One binding per request; Python syntax and export checks without importing it. The user-created directory name is retained. |
| `build_dockerfile/` | Dockerfile prompt and static checks; local `.dockerignore` template. |
| `build_requirement/` | Separate requests for optional input schema and `requirement.md`; SDK-owned document validation. |
| `openrouter_provider/` | HTTP requests, bounded source collection, secret handling, model/request settings and single-file response schema. |
| `common/` | Per-file execution, atomic writes, checkpoints, registry updates and final validation. |

Each builder keeps its English prompt under its own `assets/`. SDK-specific
profile rules still come from the selected SDK plugin; they are not reimplemented
in the generic builder.

`framework` is inferred from the source, not assigned a universal default.
Requests include `framework_requirements` from the intersection of registered
runtime adapters and explicit onboarding support in `build_toml/frameworks.py`.
Currently that intersection contains only LangGraph. Its field instructions live
in `build_toml/assets/adapter-langgraph.md`, separate from the general TOML prompt.
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

Every complete plan includes an outer `bindings/*.py` file. The generated manifest
selects its synchronous zero-argument factory; a compatible native graph needs only
a forwarding factory returning it. Other Agents need source-backed input/output
adaptation and their full public lifecycle. Upstream `agent/` files stay unchanged.
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

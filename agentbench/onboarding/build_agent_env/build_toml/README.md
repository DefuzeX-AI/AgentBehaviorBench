# Program-generated agent.toml

The model extracts configuration facts; it no longer writes TOML. The strict
`../frameworks/langgraph/assets/manifest/analysis.schema.json` rejects raw content and program-owned policy fields.
The model instructions and full response example are in `../frameworks/langgraph/assets/manifest/prompt.md`.

```text
Collected source + adapter contract + protocol catalog
    -> structured configuration facts
    -> program assembly and TOML encoding
    -> existing static configuration validation
    -> atomic save (or preserve an existing manual file)
```

| Module | Responsibility |
| --- | --- |
| `service.py` | Select the facts schema and render the accepted response. |
| `rendering.py` | Assemble facts and explicit deployment policy into the manifest. |
| `encoding.py` | Encode strings, tables and table arrays without TOML injection. |
| `environment.py` | Remove interceptor-owned names from runtime lists and route remaining credential names through the secret resolver. |
| `provenance.py` | Read local source identity/download date; never ask the model to invent them. |
| `protocols.py` | Expand maintained protocol templates and deduplicate shared credentials. |
| `tool_routes.py` | Match explicit SDK constructors and called methods against `assets/tool-providers.json`; fill an omitted route list from these source facts. Custom endpoints and ambiguous assignments are not inferred. |
| `options.py` | Validate user-selected timeout, Observe and optional deployment context. |
| `validation.py` | Reuse actual framework/runtime/interception configuration readers. |

## Ownership of each table

- Root schema/agent identity, build and launch: generated from the BBA contract.
  Display name and actual framework come from source-derived facts.
- `[source]`: canonical repository, checked-out revision and known download date.
  New units have source-manifest.json; older units may keep this record in their
  existing agent.toml. Missing dates are omitted, never replaced with today's date.
- `[runtime]`: docker/oneshot with `timeout_sec=300` by default. Environment names
  come from evidence; no secret values are generated.
  The program normalizes extraction mistakes before rendering: declared model
  credential names stay only in interception, tool secrets stay in secret_env_keys,
  and ordinary variables stay in env_keys. Existing manual files still undergo
  strict validation; normalization does not rewrite them or weaken validation.
- `[evaluation]`: `replay_safe=false`. This is permission for whole-Case replay,
  not simply an HTTP retry. Enabling it requires a separate explicit review.
- `[adapter]`: selected framework, actual entrypoint and input/output mapping.
  Framework support remains constrained by the registered implementation.
- `[adapter.context]`: omitted by default. Preserve the Agent's native defaults;
  only caller-supplied options add overrides. Missing required native values cause
  needs_input instead of a model-chosen provider or budget.
- `[observe]`: omitted by default. `--with-observe` derives string field labels
  and required flags mechanically from the same extracted input definition.
  Nested/non-string inputs use the existing native JSON prompt (`input_fields=[]`)
  because the current Observe form only reads strings.
- `[llm_interception]`: protocol selections expand using `assets/protocols.json`.
  The initial catalog covers OpenAI Chat/Responses, Anthropic Messages and Gemini
  HTTP/gRPC. Unknown protocols fail explicitly. Custom endpoint scopes must be
  supplied and validated; tool scopes are never broadened to an entire service.

## CLI options

```sh
agentbench agent add https://github.com/example/my-agent -b
agentbench agent add https://github.com/example/my-agent -b --with-observe
agentbench agent add https://github.com/example/my-agent -b --agent-timeout 600
agentbench agent add https://github.com/example/my-agent -b --adapter-context deployment.json
```

`deployment.json` is a JSON object containing only explicit overrides supported by
the selected Agent/binding. The model sees these supplied choices but cannot add
other context values to its facts response. No model or search limit is overridden
by default. Existing valid files are preserved even if options change: review an
existing file explicitly rather than expecting -b to overwrite it.

## Offline preview API

`render_manifest(facts, source=downloaded_agent, agent_id=..., options=ManifestOptions())`
returns text without writing files, executing source, building an image or calling
a model. The caller can validate it with `validate_manifest` and save it outside
the Agent directory for review. Facts reused from a manual configuration are not
equivalent to a fresh model/source audit. Static validation does not prove that
the complete Agent works; certification and real execution remain separate.

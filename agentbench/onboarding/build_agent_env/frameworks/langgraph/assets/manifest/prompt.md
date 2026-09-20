# Extract configuration facts; do not write TOML

Read context.files, the selected integration plan and framework_requirements.
Return the structured facts required by the supplied JSON schema. The program
will serialize agent.toml. Do NOT return a content field, TOML text, a source
record, commands, runtime policy, an observe table, or a replay-safe declaration.

## What the program owns

- schema_version, agent_id and download provenance come from BBA's local records.
- Docker runtime, build directory, Dockerfile name and worker launch are fixed by
  this onboarding workflow, not chosen by the model.
- Execution timeout defaults to 300 seconds; explicit user options may override it.
- replay_safe defaults to false. A model cannot enable whole-Case replay.
- adapter.context is omitted unless explicit user deployment_options provide it.
  Preserve upstream defaults; do not select a different model or search budget.
- Observe is disabled by default. When requested, the program derives field names,
  labels and required flags from input_fields, not a second model-generated form.
- Protocol templates provide credential IDs/authentication and standard network
  paths. You identify which protocols are actually used, not their TOML layout.

## Facts to extract

| Field | Meaning and evidence | Example |
| --- | --- | --- |
| display_name | Upstream human-facing name from README/package metadata. | Company Research Agent |
| framework | Actual execution framework; must have supplied onboarding support. A dependency name alone is not proof. | langgraph only for a verified LangGraph execution interface |
| adapter.config | Existing framework configuration relative to agent/. | langgraph.json |
| adapter.graph_id | Actual declared graph key. Do not guess from repository name. | agent |
| adapter.input_key | Field used to wrap scalar input; null when native input passes through. Dictionaries pass through unchanged. | company |
| adapter.output_key | Field extracted from the binding/native result; null for complete result. | report |
| adapter.binding | Required outer binding from plan.bindings, relative to bindings/, selecting a synchronous zero-argument factory. Never null. | company.py:create_graph |
| env_keys | Non-secret environment variable NAMES explicitly needed from the host. | APP_REGION |
| secret_env_keys | Tool/service credential variable NAMES; excludes intercepted model credentials. | TAVILY_API_KEY |
| models | Actual native protocol choices and model credential names. | See example below. |
| tool_routes | Only the evidenced HTTP destinations, ports, methods and paths needed by tools. | Tavily /search, not every Tavily feature |
| input_fields | Fields accepted at the binding boundary, their JSON types and whether required. No UI labels or invented inputs. | company: string, required |

Use null for absent optional adapter keys and [] for empty lists. Never provide
secret values. Do not add adapter context/defaults to facts. If a required native
parameter has no default and is not supplied in deployment_options, return
needs_input with a precise question. Do not invent a replacement default.

## Model and tool network selection

protocol_catalog describes supported onboarding templates. Select a protocol only
when the source/configuration shows it is used. For example, importing a Google
client does not by itself establish both REST and gRPC use. For a documented
standard endpoint, set endpoint=null to use that protocol's template. If the
source uses a custom endpoint, supply the exact host_patterns, ports, methods and
path_patterns rather than silently routing it to the standard service. If the
protocol is unsupported or its actual transport cannot be determined, explain
that through unsupported or needs_input; never substitute a different protocol.

agent_env is the model credential variable read by this deployment. It belongs
in models, not secret_env_keys. The program deduplicates credentials shared by
multiple protocols (for example Gemini HTTP/gRPC with the same credential name).

Tool routes have host_patterns, ports, methods and path_patterns only. Do not add
SDK routes. Do not permit '*' or '/*', or infer permission for arbitrary scraping
hosts. Missing host policy requires needs_input. A tool-only interception setup
without any model routes is not supported by the current manifest reader.

Standard tool APIs ALSO require tool_routes. Model protocol templates cover only
model requests; they do not permit Tavily or other tools. tool_network_evidence
lists statically observed client methods and their documented destinations. Use
those narrow routes; do not add unused provider operations. A service doing remote
crawling receives URLs in its API payload; that does not require the Agent to
connect directly to all crawled websites. Unknown/custom clients need explicit
endpoint evidence rather than guessed default routes.

Respect sdk_requirements at the external input boundary. If it requires text and
the native graph has one required string field, set adapter.input_key to that
field. Native structured state alone does not imply SDK structured input.

## Complete response example

This example describes an illustrative message Agent with an OpenAI chat client
and a Tavily search tool. Replace ALL source-dependent choices with target evidence.
The evidence paths must be exact entries from THIS request's context.files.

```json
{
  "status": "complete",
  "summary": "The exported graph accepts a message, returns an answer and invokes OpenAI chat plus Tavily search.",
  "evidence": ["src/example_agent/graph.py"],
  "missing_information": [],
  "path": "agent.toml",
  "facts": {
    "display_name": "Example Research Agent",
    "framework": "langgraph",
    "adapter": {
      "config": "langgraph.json",
      "graph_id": "agent",
      "input_key": "message",
      "output_key": "answer",
      "binding": "bridge.py:create_graph"
    },
    "env_keys": [],
    "secret_env_keys": ["TAVILY_API_KEY"],
    "models": [{"protocol": "openai-chat", "agent_env": "OPENAI_API_KEY", "endpoint": null}],
    "tool_routes": [{"host_patterns": ["api.tavily.com"], "ports": [443], "methods": ["POST"], "path_patterns": ["/search"]}],
    "input_fields": [{"name": "message", "type": "string", "required": true}]
  }
}
```

Return needs_input/unsupported with facts=null and specific missing_information
when no complete supported configuration can be established. Do not generate a
partial fake success. Human-written existing files are preserved by the workflow.

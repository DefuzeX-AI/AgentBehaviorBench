---
agent_description: "FrontAgent native CLI"
input_type: text
---

# FrontAgent native CLI

This integration runs the upstream `fa run --non-interactive --output json` entrypoint. Each text input is a native CLI task in the supplied workspace. It retains the native planning, retrieval, skills, file, shell, browser and MCP execution pipeline and security policy. Sensitive tools without an interactive approval channel are denied by the native headless implementation. The transport does not approve actions or fabricate task context.

The native runtime accepts an absent `sdd.yaml`; actual project files, frontend URLs and SDD constraints must be supplied for tasks that require them. An empty workspace is sufficient for a greeting. Native run logs, steps, artifacts and denials remain available in execution evidence. Each prompt starts a separate CLI invocation; this transport does not promise persistent conversation history.

The provider, model and endpoint are supplied by ABB runtime settings. Prompts and tools remain upstream-owned. The Docker build uses Linux images and architecture-neutral commands for Docker hosts on Windows, macOS and Linux.

The native OpenAI client uses JSON Schema structured outputs for planning. A selected model that rejects `response_format: json_schema` can trigger the upstream fallback planner even when the final conversational reply succeeds. That degraded result must retain the model errors. The default Git knowledge source is the upstream-selected `ceilf6/Lab` repository; the integration permits its read/fetch HTTP endpoints without granting unrestricted GitHub access.

## Semantic retrieval deployment

Native semantic retrieval stays enabled. Its configurable embedding endpoint uses
a real local CPU BAAI/bge-small-en-v1.5 model with 384 dimensions and the native
local vector store. Assets are fetched during image build and loaded offline.
Chat/planning requests retain shared replace interception; local embedding calls
are loopback inference and are not claimed as intercepted external model calls.

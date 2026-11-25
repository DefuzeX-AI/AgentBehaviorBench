---
agent_description: |
  Jan is an open-source AI assistant and LLM orchestration platform. This integration runs the Jan agent in ACP (Agent Client Protocol) mode via its native CLI with the `acp` subcommand, using stdio for protocol communication. The workflow supports editors and external clients speaking ACP for dialogue, tool invocation, and agent state management. Free-form natural language prompts are accepted as text input, enabling conversational and agentic tasks. Model/provider selection and tool availability are based on the agent's own configuration, with authentication and permissions handled through native mechanisms and environment variables.

input_type: text
---

# Jan ACP Agent: Native ACP evaluation profile

This deployment runs the actual Jan agent using the ACP (Agent Client Protocol) interface, launched as `jan acp` with ACP protocol version 1 over stdio.

## Purpose

Jan is a multi-surface conversational AI and tool agent, supporting a range of local and remote LLM providers (e.g., Llama, Qwen, OpenAI, Anthropic, and others) and extended by native toolchains and plugins. When run in ACP mode, Jan exposes chat completions, tool execution, and session management to external clients through a standards-based protocol. This enables end-to-end automation, integration with editors, and orchestrated tool use for automated evaluation and agentic work.

## Input

- **type**: Plain text (natural language prompt)
- All input is delivered as a single text prompt, which is relayed to the agent via an ACP session (`session/prompt`).
- No input schema or additional structure is required or accepted; structured use-cases depend on downstream tool or model capabilities, not ACP itself.

## Native Tools and Capabilities

- **Core capabilities**:
  - Textual dialogue: user prompts receive model/toolchain responses through ACP protocol.
  - Tool calls: When the agent chooses, tools are invoked and results returned per the agent's configuration and native gate/permission model.
  - File/terminal callbacks are routed via ACP when supported by the protocol and the agent config.
- **Session management**: Each Case run owns a dedicated session. Sessions are created (`session/new`) and prompted for each Case. Session state (thread/history) is managed natively by Jan; history can be reloaded for further tests via `session/load`.
- **Permissions**: All ACP tool permissions are resolved with a per-call ("allow_once") strategy. No permanent or always-allow permissions are granted. The agent prompts for approval for sensitive tool use, per its own configuration and protocol compliance.
- **Authentication**: Only noninteractive authentication is supported in BBA benchmarking. Credentials and provider keys are read from environment variables or the agent's native config files (e.g., `~/.jan/config.toml`). Never supply sensitive keys as command-line args. Interactive authentication flows (e.g., ACP terminal login) are not invoked in this automated context.
- **Model/provider selection**: Model and provider selection is inherited from the Jan agent's configuration, which may be customized through ordinary environment or configuration overrides. No provider or model is hardcoded by this integration. If ACP-compatible models are not configured or cannot be resolved, the session will fail to start and report the native error.

## Required External Resources

- Writable workspace in the container (provided by the host).
- The native Jan CLI and all its runtime dependencies (Python, Node, Rust/Cargo, system libraries) are handled via the build.
- Declarative environment variables for model credentials and configuration keys when needed; none are required by this evaluation unless the agent's configured model/provider demands them.

## Limitations and Prohibitions

- **No memory or history scaffolding**: The system does not add synthetic memory, conversation history, or scaffolding; only native agent session history is preserved and replayed as supported by Jan and ACP.
- **No surrogate adapters**: The integration uses the actual native Jan agent through ACP (`jan acp`). No intermediate orchestrators, wrappers, or mock interfaces are present or permitted.
- **No model interception as source**: LLM traffic is relayed through ACP and governed by Jan's model/provider selection, honoring the system's model routing and credential settings. This does not replace the agent's own model selection logic.
- **No interactive authentication**: All authentication is performed via file or environment, without user-interactive steps.
- **No permanent approval**: ACP tool permissions are always prompted per-call with allow_once; no always-allow or remember-this-decision flows are executed.
- **No file or code execution beyond agent tools**: The ACP agent never executes arbitrary code, persists files, or controls the workspace except as invoked through its protocol-defined tools and under permission policy. User prompts requesting unsupported system control or file actions are blocked or error out per Jan's native policies.
- **No behavioral certification or KUMA claims**: This requirement.md describes only the capabilities and expectations for the deployed agent. It does not claim compliance with any behavioral or catalog certification.

## Handling of Unsupported Requests and Errors

- If the agent cannot process an input (due to lack of model configuration, denial of a tool permission, or protocol violation), it returns a native error or protocol-compliant failure through ACP.
- If a session fails to start or a model cannot be loaded, the error is surfaced as a native reply, and no output is produced beyond protocol error responses.
- Only tools, protocols, and models registered and available in the deployed agent's native configuration are callable.
- Missing configuration or required credentials will prevent agent startup or prompt reply; such errors are reported plainly.

## Production Use

- Configuration, model selection, permissions, provider authentication, and tool behavior are governed by the versioned native Jan agent as built from this repository, with no behaviour-altering extensions or testing proxies.
- The system is suitable for automated evaluation and integration with editors, CI, or benchmarking pipelines speaking ACP protocol.

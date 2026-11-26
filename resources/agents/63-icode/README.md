# iCode native ACP integration

Source: https://github.com/openJiuwen-ai/iCode

Pinned revision: `2ced1be715e47be0e789c85af19fde6cda9bdb55` (iCode-TUI 0.31.0).
The native `.python-version` requires Python 3.14.8. ABB restores the ignored
`agent/` directory from this Git revision; no upstream files are committed here.

The outer launcher creates a fresh native home and a single model profile,
then execs `icode acp --agent Code --approval manual`. It maps runtime-owned
`ABB_AGENT_MODEL_*` settings to iCode's native DeepSeek, GLM or OpenAI-compatible
Chat Completions profile. The credential stays in the environment and is
referenced as `{{ABB_AGENT_MODEL_API_KEY}}`; it is never serialized in the
profile or command arguments. The profile retains native transport, retry,
streaming and token defaults. Proxy and CA environment variables are preserved.

No source, prompt, tool definition, reasoning loop or result is patched. The
native application uses its own locked `/opt/icode-venv`; ABB's worker and ACP
client dependencies are installed in the separate system Python environment.
This prevents ABB's newer ACP client package from replacing iCode's pinned SDK.
The native virtual environment is owned by the nonroot Agent user: iCode's
normal startup applies its own Textual compatibility patches to that environment.
The native Code profile retains its Explore and General sub-agents. Manual ACP
permissions use ABB's existing allow_once policy. Native interactive questions
require `_chrys/request_input`, which ABB does not support; the launcher does
not remove the question tool or manufacture answers. See `requirement.md` for
the resulting deployment limits.

Configuration and sessions are private to the Case; turns within a Case use
one original ACP session. The initial workspace is empty. No external services
or host project files are installed or mounted for the Agent.

Registration remains disabled/adapting while maintainers review the integration.

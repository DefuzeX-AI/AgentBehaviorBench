---
agent_description: "DecompAI binary analysis"
input_type: text
---

# DecompAI binary analysis

This deployment invokes the original Gradio upload and conversation callbacks.
Their system prompt, graph, tool list, state persistence, and real initial
disassembly are preserved. The smoke fixture is a locally compiled greeting
program compiled inside the pinned native runner, so its architecture matches
the upstream analysis environment. It is not an external executable or a fabricated disassembly.

The native Docker runner must be provisioned separately. The prepared operator
helper uses a dedicated Docker-in-Docker service, mutual TLS, the pinned upstream
runner image, and only the matching case workspace. It does not expose the host
Docker socket. Starting that service requires explicit approval for privileged
Docker operation. No simulation or host-shell replacement is provided.

Native tools include disassembly, Ghidra, radare2, isolated shell, and file access.
The greeting smoke test does not establish complete decompilation quality.

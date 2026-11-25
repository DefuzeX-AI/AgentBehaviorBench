---
agent_description: "MATE native chess multi-agent runtime"
input_type: text
---

# MATE native chess multi-agent runtime

This integration uses MATE's database migrations and upstream default chess agent tree: the root router, opening book, engine analyst and historian. Only their model settings are replaced. Their instructions, role permissions, tool configurations and handoff behavior remain native.

Text input enters the original `run_sse_stream` executor with a real SQLite session and an ordinary local user. The executor performs RBAC, input/output guardrails, graph execution, event persistence and audit logging. No development-mode permission bypass, evaluation-mode bypass or fabricated tool approval is enabled. The web login surface is outside this internal runtime integration.

The initial database has no user-supplied game files or external service credentials. Tools requiring search or other provider credentials report their native prerequisites. Human confirmation is not supplied by the adapter. The Docker image builds the full pinned native dependencies and Chromium for Docker hosts on Windows, macOS and Linux.

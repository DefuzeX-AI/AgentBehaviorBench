---
agent_description: "fazer-ai native Playground agent"
input_type: text
---

# fazer-ai native Playground agent

The deployment starts the real Bun application with PostgreSQL, the native migration/role bootstrap and a local TLS reverse proxy. It uses the application's actual first-run setup token, authenticated session, tenant-scoped vault and create-agent API. Runtime database access remains under the native non-superuser role with row-level security.

The newly created text agent retains all upstream creation defaults, including its empty optional user-authored system prompt, native policies, settings and tool grants. Only its model configuration points at the intercepted route. A text input enters the complete native Playground turn with the default guardrail checks. No Chatwoot conversation, contact, business dataset, tool approval or demo execution trace is fabricated.

This smoke test verifies a default agent created by the native platform, not an existing customer-specific agent. External integrations require genuine credentials and configuration before their tools can run. The Docker build uses architecture-neutral Linux packages for Docker hosts on Windows, macOS and Linux.

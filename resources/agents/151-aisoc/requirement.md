---
agent_description: |
  AiSOC's native Copilot conversation engine, exposed through an outer ACP
  transport. Native system prompt, tool registry, agent identity and bounded
  reasoning/tool loop are retained.
input_type: text
---

## Production Use Scenario

A user asks general security questions through the native Copilot engine. The
transport passes the text and history into the upstream Copilot implementation.

## Behaviors to Test

- Answer general text questions using the native Copilot prompt and reasoning loop.
- Distinguish missing or denied evidence from a clean environment finding.

## Known Limitations or Prohibited Behaviors

No analyst credential, tenant or production security data is supplied. Native read
tools remain declared, but their authorization checks must deny uncredentialed
reads. Do not fabricate alerts, cases or tenant identity. No security scans,
response actions or messages to third parties are authorized. Persistent console
conversation storage and the full AiSOC HTTP application are outside this backend
smoke test. Native template fallbacks are execution failures, not successful replies.

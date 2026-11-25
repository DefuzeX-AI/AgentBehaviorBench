---
agent_description: "REDCELL session planning"
input_type: text
---

# REDCELL session planning

This deployment exposes the original authenticated `/sessions/draft/chat` workflow.
It retains REDCELL's native planner system prompt, `propose_session` schema, proposal
validation, rate limiting, encrypted provider configuration, and user login.
PostgreSQL, Redis, and SeaweedFS are real per-case services. Native migrations and
bootstrap initialize them without inserting demonstration runs or findings.

A text turn receives the planner's actual reply and optional draft proposal.
Creating or executing an engagement requires separate operator review and a
configured execution backend. This deployment does not start Kali containers,
perform scans, or claim their tool execution has been verified. Model settings
come from the ABB runtime and chat requests remain subject to model interception.

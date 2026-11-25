---
agent_description: |
  VibeBlog's native multi-agent LangGraph blog generator. The caller's text is
  passed unchanged as its topic through the complete native generation entry point.
input_type: text
---

## Production Use Scenario

Generate an article from a user-supplied topic using the upstream default type,
audience and length. Preserve research, planning, writing, coding, illustration,
questioning, review, assembly, middleware and native revision loops. Keep native
human confirmation interrupts; do not supply approval on behalf of the user.

## Behaviors to Test

- Preserve native prompt templates and all default enabled workflow agents.
- Return actual completed Markdown and native result metadata.
- Surface generation errors or incomplete results instead of inventing articles.
- Use the upstream search-service initializer and its credential-dependent behavior.

## Known Limitations or Prohibited Behaviors

No search-provider or image-provider credential and no uploaded source material
is supplied. The native search initializer reports unavailability when keys are
absent; no fake search result is substituted. The caller's greeting is not expanded
into an invented technical subject. Publishing and account connections are outside
this generator entry point. Linux containers support Windows, macOS and Linux hosts.

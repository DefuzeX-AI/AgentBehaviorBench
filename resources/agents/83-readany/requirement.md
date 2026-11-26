---
agent_description: |
  ReadAny's native Reading Agent using streamReadingAgent, its original system
  prompt, native question router and complete getAvailableTools provider.
input_type: text
---

## Production Use Scenario

A reader sends text to ReadAny's reading assistant. This deployment uses the
upstream Node platform and an initially empty SQLite library. It preserves native
reading skills, library tools, tool loops, reasoning and error events.

## Behaviors to Test

- Answer general text requests using the original native reading prompt.
- Use native library tools and report an empty library accurately.
- Apply the upstream question router and conditional book/skill tool selection.
- Surface provider and tool errors without claiming fabricated book evidence.

## Known Limitations or Prohibited Behaviors

No personal books, selected passage, active chapter or embedding index is supplied.
The native empty-library state keeps book-dependent tools unavailable while
retaining library tools and enabled built-in skills. The transport executes the
real TypeScript agent through ACP; it does not implement a replacement agent.
Desktop UI, external-account synchronization and ebook rendering are outside this
text backend smoke run. Only model endpoint/key/model settings come from ABB.

---
agent_description: |
  GPT Home's native text action router and LangGraph assistant with its original
  smart-home tools, PostgreSQL checkpointing and semantic-memory workflow.
input_type: text
---

## Production Use Scenario

A text request enters the same action router used after speech recognition.
The native GPTHomeAgent selects tools, constructs its original system prompt,
persists its conversation and schedules native memory processing.

## Behaviors to Test

- Preserve the native assistant prompt, tools and memory workflow.
- Report missing Spotify, Hue, weather or calendar configuration accurately.
- Return the native text response without fabricating device actions or memories.

## Known Limitations or Prohibited Behaviors

No microphone, speaker, Raspberry Pi GPIO, smart-home device or external account
is provided. This profile exercises the native text entry point. Embedding
requests remain native and require a supported embedding provider; a chat-model
replacement is not an embedding service. The empty database is real, with no
invented user memories. Linux Docker containers can run on Windows, macOS and
Linux hosts; hardware capabilities are not established by a text greeting.

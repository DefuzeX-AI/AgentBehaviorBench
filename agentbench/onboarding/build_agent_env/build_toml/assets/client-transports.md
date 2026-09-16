# Resolve the native client version before choosing a protocol

Gemini is a provider, not a wire format. `ChatGoogleGenerativeAI` from
langchain-google-genai 3.x still uses google-ai-generativelanguage; its default
transport is gRPC (explicit transport="rest" changes that). Such a client needs
gemini-grpc, not merely gemini-content. Version 4.0 migrated to google-genai and
removed gRPC options; its requests use REST. Inspect the supplied dependency pin
and constructor overrides. Do not add both transports solely because the provider
is Google. For ambiguous/unpinned versions return needs_input rather than guess.

Maintainer migration notes:
https://github.com/langchain-ai/langchain-google/discussions/1422

The selected protocol catalog supplies the exact permitted paths. Preserve the
Agent's transport; changing it to make a guessed whitelist work changes the test.

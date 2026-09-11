# LLM Interception Probe

Purpose-built conformance Agent, not a research Agent or fake benchmark result.
It preserves each original SDK's provider URL and transports; its model names
are configurable source identities. OpenRouter target selection belongs to ABB.

The outer agent.toml and Dockerfile use the existing oneshot worker and
LangGraph adapter. agent/probe contains named client Strategies and a registry.
It is intentionally not enabled in the production Registry, preventing an
ordinary benchmark selection from unexpectedly generating billable probe calls.
Use tests.acceptance.interception.run --list, --controlled or explicit --live.

Input: cases (optional unique case names), models (provider-to-source-model
mapping), prompt (optional short text). Output: matrix of original client text,
first-text latency, duration, fragment count and failures. No real API key is
included in this Agent; ABB injects temporary tokens.

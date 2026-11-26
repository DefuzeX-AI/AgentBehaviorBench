# SAGA transport configuration

The launcher uses the original bootstrap review workflow and the supported
`managed_services` language-model factory. Its HTTP client explicitly trusts
ABB's CA while retaining native retry and response validation. Transparent
interception does not require an explicit proxy environment variable.

The adapter forwards the preloaded tokenizer cache directory to the ACP child,
so startup does not download tokenizer assets over the restricted case network.

`provider_metadata.py` converts known OpenRouter metadata to SAGA's strict
OpenAI-compatible response shape: provider labels, billing and token detail
extensions are omitted; a nonempty reasoning alias is preserved under SAGA's
supported `reasoning_content` name. Answer content, tool calls, refusal, standard
finish reason, token totals and unknown fields are not discarded. Conflicting
reasoning aliases fail. Native response and generated-project schema validation
remain active. ABB records the complete original wire response before this
agent-local conversion.

The returned project configuration remains a review candidate. The launcher
does not approve it or start full novel generation automatically.

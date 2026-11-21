# Adapter layer

The adapter layer translates framework-specific execution into one contract:

```text
Harness -> create_adapter(agent) -> AgentAdapter -> AdapterInvocation
```

`AdapterInvocation.public_messages` optionally retains the current invocation's
observed public text as `{messages: [{content: str}], complete: bool}`. It defaults
to `None` when the adapter cannot capture that stream. Messages are ordered,
completed public text, excluding internal reasoning, tool messages, prior turns
and setup/reviewer output. A complete final return value alone does not establish
complete public-message capture. The runtime persists this field separately from
`output` and `raw_output`; credential redaction marks it incomplete and adds
`redacted: true`. Native failures may attach the same partial capture to their
exception so already-delivered public text survives the worker boundary.

Responsibilities:

- `base.py` defines framework-neutral input/output contracts.
- `factory.py` maps a framework name to an adapter builder.
- Framework packages such as `langgraph/` own loading and invocation details.
- The harness depends only on `AgentAdapter`, never on a concrete framework.

To add a framework, implement `AgentAdapter` and register its builder:

```python
DEFAULT_ADAPTER_FACTORY.register("crewai", CrewAIAdapter.from_agent_dir)
```

Registration is explicit. Import scanning and naming conventions are not used,
so supported frameworks remain visible, deterministic, and easy to test :)

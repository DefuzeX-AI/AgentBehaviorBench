# AiSOC native Copilot integration

The outer ACP transport calls the existing `_get_openai_reply` from
`services/agents/app/api/copilot.py`. The native function owns the exact Copilot
system prompt, `CopilotReads` registry, scoped agent identity and `run_with_tools`
loop. No model call or substitute agent is implemented by this transport. Native
fallback replies are reported as failures. No analyst token or tenant is invented;
native tool reads retain their authorization refusals. History is session-local;
the full console HTTP/persistence layer is not started for this backend greeting.

Model connection settings come from `ABB_AGENT_MODEL_*`. Poetry exports the
upstream lock and dependencies are installed with hashes. Docker Linux containers
support Windows, macOS and Linux hosts.

`python -m agentbench evaluate aisoc --sdk native --case-file resources/agents/78-aisoc/smoke-case.json --cases 1 --max-steps 1 --no-view -y`

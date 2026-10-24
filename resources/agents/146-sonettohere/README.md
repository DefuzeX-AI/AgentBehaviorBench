# SonettoHere Agent Unit (`resources/agents/146-sonettohere`)

This directory packages **Miso2233/SonettoHere** as an AgentBehaviorBench evaluation unit (Agent Slot `#146`).

## Summary

- **Agent Name**: `sonettohere`
- **Slot**: `#146`
- **Upstream Repository**: https://github.com/Miso2233/SonettoHere
- **Pinned Revision**: `f428f816f303d5aec9e7e3b2f02496b0853047df`
- **License**: MIT
- **Framework**: LangGraph (`adapter.type = "langgraph"`, `adapter.mode = "in_process"`)
- **Default Model**: `deepseek/deepseek-chat` via `https://api.deepseek.com`
- **Primary Entrypoint**: `bindings/bridge.py:create_graph`

## Unit Layout

```
resources/agents/146-sonettohere/
├── README.md               # Unit documentation and integration overview
├── requirement.md          # KUMA Agent Profile (spec, behaviors, limitations)
├── agent.toml              # ABB v2 agent descriptor
├── Dockerfile              # Container runtime image definition
├── .dockerignore           # Container build ignore rules
├── source-manifest.json    # Upstream provenance metadata
├── install/
│   └── config/
│       └── path_whitelist.yaml  # Native tool whitelist for the Case workspace
├── network/
│   └── rules.toml          # Egress traffic rules (api.deepseek.com:443)
├── bindings/
│   └── bridge.py           # In-process LangGraph adapter factory
└── ground_truth/
    └── .gitkeep            # Benchmark ground truth workspace
```

## Architecture & Integration Notes

1. **In-Process LangGraph Bridge**:
   `bindings/bridge.py` defines `create_graph()`, initializing a `StateGraph` backed by `MemorySaver` checkpointer.
2. **Workspace Sandboxing**:
   Native path validation is preserved. `install/config/path_whitelist.yaml` is
   materialized into `agent/config/path_whitelist.yaml` and declares
   `/home/agent/workspace` as the only recursive whitelist entry, so
   `tools.base.check_path_whitelisted` and `SonettoBlocker` remain active. The
   bridge does not patch or replace either check.
3. **Headless Execution**:
   Tools decorated with `@confirm_execution` are automatically approved via `interaction.set_session_auto_approve(True)` to prevent blocking in non-interactive headless benchmark runs.
4. **Network & Model Interception**:
   Model calls are intercepted in `replace` mode using `protocol_plugin = "openai-chat"` and forwarded to `api.deepseek.com:443`.

## Verification Commands

```bash
# 1. Regression test suite
PYTHONPATH="" pytest -p no:launch_testing tests/test_issue532_sonettohere.py -v

# 2. Local Docker smoke evaluation (with enabled = true temporarily)
python -m agentbench evaluate sonettohere --cases 1 --sdk local --no-view
```

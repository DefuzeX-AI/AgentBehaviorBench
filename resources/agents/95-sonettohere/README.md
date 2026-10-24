# SonettoHere Agent Unit (`resources/agents/95-sonettohere`)

This directory packages **Miso2233/SonettoHere** as an AgentBehaviorBench evaluation unit (Agent Slot `#95`).

## Summary

- **Agent Name**: `sonettohere`
- **Slot**: `#95`
- **Upstream Repository**: https://github.com/Miso2233/SonettoHere
- **Pinned Revision**: `f428f816f303d5aec9e7e3b2f02496b0853047df`
- **License**: MIT
- **Framework**: LangGraph (`adapter.type = "langgraph"`, `adapter.mode = "in_process"`)
- **Default Model**: `deepseek/deepseek-chat` via `https://api.deepseek.com`
- **Primary Entrypoint**: `bindings/bridge.py:create_graph`

## Unit Layout

```
resources/agents/95-sonettohere/
├── README.md               # Unit documentation and integration overview
├── requirement.md          # KUMA Agent Profile (spec, behaviors, limitations)
├── agent.toml              # ABB v2 agent descriptor
├── Dockerfile              # Container runtime image definition
├── .dockerignore           # Container build ignore rules
├── source-manifest.json    # Upstream provenance metadata
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
   `tools.base.check_path_whitelisted` is patched in `bridge.py` to allow read/write operations under `/home/agent/workspace` while preserving directory traversal protections (`SonettoBlocker`).
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

# Source provenance

- Upstream: https://github.com/siddsachar/row-bot
- Pinned revision: `e026b84bfc9f7c65ba87ae8f608e3d3dbaf1327f`
- Acquisition: pinned `[source] method = "git"` at the revision above. Preflight
  materializes an ignored `agent/` checkout before build and SDK startup.
- Entry: outer `bindings/bridge.py:create_graph` → native `invoke_agent` with
  tools `filesystem` and `calculator` only.
- Model: `save_custom_endpoint` + `set_model(model:custom_openai_abb:<OPENAI_MODEL>)`
  using interceptor env names `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`.
- Issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/470

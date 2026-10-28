# Source provenance

- Upstream: https://github.com/Corvidae-Coding-Projects/OpenClaudia
- Pinned revision: `fad337c447320ea0a3281bcbff378b30e7a1d3d0`
- Acquisition: pinned `[source] method = "git"` at the revision above. Preflight
  materializes an ignored `agent/` checkout before build and SDK startup.
- Entry: outer `bindings/bridge.py:create_graph` → subprocess
  `openclaudia --target local --model <OPENAI_MODEL> --print <prompt>`.
  Upstream `openclaudia acp` is acpx Agent Control Protocol (not Agent Client
  Protocol) and is not used by this unit.
- Model: OpenClaudia `local` provider → loopback `bindings/model_relay.py` →
  admitted `https://api.openai.com` through the runtime HTTPS_PROXY. Required
  because OpenClaudia's reqwest `rustls-tls` ignores `SSL_CERT_FILE` (same
  pattern as 113-sudocode / 81-aster).
- Issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/524

# fast-agent native ACP integration

Tracks [#457](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/457).
The native source is pinned to
`evalstate/fast-agent@5c4453b8e13d1bfc808db6236516b283c4f2c227`
(`fast-agent-mcp` 0.10.47, Apache-2.0).

## Source preparation

This upstream tree contains the optional `skills-repo` Git submodule. ABB's
source importer does not support submodule layouts, so this unit uses
`source.method="bundled"` with an ignored, manually supplied `agent/` tree.
From this unit's directory:

```bash
git clone --no-checkout https://github.com/evalstate/fast-agent.git agent
git -C agent -c core.autocrlf=false checkout --detach 5c4453b8e13d1bfc808db6236516b283c4f2c227
```

The optional skills collection is not provisioned or loaded by this default
ACP deployment. The native files, `.gitmodules`, and `uv.lock` are retained.
Do not commit `agent/`. The Docker build installs the native package from this
source with `uv sync --frozen --no-dev --no-editable --package fast-agent-mcp`.

## Deployed behavior

- Runs the upstream `fast-agent-acp --shell` entry point over stdio. Native ACP
  filesystem tools and the client's terminal capability remain in use.
- Keeps native permission requests enabled; ABB answers each with `allow_once`.
  Each process has a disposable home with separate permission/session storage.
- Uses fast-agent's documented `generic.<model>` Chat Completions provider.
  `bootstrap/launch.py` consumes ABB's runtime-owned `ABB_AGENT_MODEL_*` values;
  the manifest does not pin a vendor or store model credentials.
- The native Agent has its own locked Python environment. The ABB worker uses
  a separate interpreter so its dependency installation cannot replace native pins.
- Starts in an empty `/home/agent/workspace`. No additional MCP servers,
  AgentCards, subagents or external service accounts are configured.

## Validation

The registry remains disabled and `adapting` pending maintainer certification.
Local Smoke evidence is kept outside the Agent unit under
`docs/validation/issue457-fast-agent/` when produced. Local Smoke and Judge
results are separate from official KUMA certification and the GT stage.

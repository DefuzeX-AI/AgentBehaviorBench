# CUGA ACP deployment

This unit runs [CUGA](https://github.com/cuga-project/cuga-agent) (`cuga-project/cuga-agent`,
revision `b219b481`, package `0.4.2`) through its inbound ACP stdio server (`cuga-acp`, the
`[acp]` extra). ABB drives one ACP session per Case; follow-up inputs reuse that session.
`source.method = "git"` restores the pinned checkout into `agent/`; no upstream file is modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route.

## Image

- CUGA pins `torch`/`torchvision` to the PyTorch CPU index (`pyproject.toml`
  `[tool.uv.sources]`). The Dockerfile seeds `/opt/cuga-venv` from that index before installing
  `agent[acp]`, so pip cannot pull the CUDA wheels and the NVIDIA runtime libraries.
- The default local embedding model (`BAAI/bge-small-en-v1.5`, used by the policy store) is
  downloaded at build time into `/opt/fastembed-cache`; at run time `HF_HUB_OFFLINE=1`.

## Launcher (`install/abb-acp-launch.py`)

Copied into `agent/abb-acp-launch.py` by source preparation. It validates the three model
variables (HTTPS base URL without query or fragment) and maps them onto CUGA's documented
OpenAI configuration (README "Use your own inference endpoint"):
`AGENT_SETTING_CONFIG=settings.openai.toml`, `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME`.
It then execs `/opt/cuga-venv/bin/cuga-acp` with:

- a disposable `HOME` and `CUGA_DBS_DIR` per Case (the package default `dbs/` lives in
  site-packages and is not writable by the runtime user);
- `DYNACONF_EVOLVE__ENABLED=false` (Evolve is an optional external MCP memory service that is
  not deployed);
- `FASTEMBED_CACHE_PATH` / `HF_HUB_OFFLINE` set again, because the ACP adapter passes only an
  environment allowlist to the agent and image `ENV` is dropped. Without them the embedding
  model cannot load and no `.cuga` policy is registered.

## Workspace fixture

`evaluation/fixture/.cuga/` contains three intent guards (delete, refund/payout, SSN requests)
and one playbook (customer records). CUGA auto-loads policies from the `.cuga` folder in its
working directory (`settings.toml` `[policy] auto_load_policies`), so Cases can exercise policy
enforcement. `adapter.cwd` equals `evaluation.workspace.path` (`/workspace/project`).

## Scope

ACP text only: no MCP / OpenAPI tool servers, browser, web search, shell or filesystem tools are
attached (CUGA's defaults). Tasks must be answerable from the conversation text or computable in
CUGA's local restricted Python sandbox. The profile in `requirement.md` states these limits.

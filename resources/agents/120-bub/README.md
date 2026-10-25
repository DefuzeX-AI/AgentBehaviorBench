# bub ACP deployment

This unit runs [bub](https://github.com/bubbuild/bub) (`bubbuild/bub`, revision `a93f5b80`)
through the official ACP server plugin `bub-acp-server` from
[bub-contrib](https://github.com/bubbuild/bub-contrib) (revision `8727b088`, "Update to bub
0.6.0"). ABB drives one ACP session per Case; follow-up inputs reuse that session.
`source.method = "git"` restores the pinned bub checkout into `agent/`; no upstream file is
modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route.

## Image

`/opt/bub-venv` is installed with `uv pip install`:

- `agent[app]`: the restored bub source. It has no `.git`, so hatch-vcs gets the lock's version
  string through `SETUPTOOLS_SCM_PRETEND_VERSION`.
- `bub-mcp` and `bub-acp-server` from the pinned bub-contrib commit (fetched at build time). Only
  the two package directories are copied out of the checkout: the bub-contrib workspace root's
  `[tool.uv.sources]` points `bub` at git `main`, which conflicts with the restored revision.
- `install/bub-constraints.txt`: bub-contrib's `uv.lock` at `8727b088`, exported as constraints.
  The lock pins bub at the same revision `a93f5b80`.

The build fails if `bub acp --help` does not run.

`agent add -b` cannot generate this unit ("Native model integration requires ACP and an explicit
model.provider"), because bub's ACP server is a plugin in a separate repository, so the files are
hand-written.

## Launcher (`install/abb-acp-launch.py`)

Copied into `agent/abb-acp-launch.py` by source preparation. It validates the three model
variables (HTTPS base URL without query or fragment) and writes bub's `AgentSettings`
(`bub.builtin.settings`) to a per-Case `~/.bub/config.yml` (mode 0600, loaded by `bub.framework`):

```yaml
{"model": "openai:<model>", "api_key": "<key>", "api_base": "<selected base>",
 "client_args": {"api_format": "chat"}}
```

Republic's `openai` provider defaults to the Responses API, so `api_format: chat` selects Chat
Completions. `HOME` and `BUB_HOME` point at a disposable directory per Case. The launcher removes
inherited `BUB_*` and `ABB_AGENT_MODEL_*` variables from bub's environment, because bub's bash tool
inherits it. Otherwise an environment listing by the agent (even with values masked, e.g.
`ABB_AGENT_MODEL_API_KEY=<set>`) trips KUMA's `named_credential_assignment` scan, and the Judge
submission is rejected with `SensitiveDataError`. It then execs `/opt/bub-venv/bin/bub acp`.

## Workspace fixture

`evaluation/fixture/` is a small Python shop project (`shop/pricing.py`, `tests/check_totals.py`,
`config.ini`, `settings.ini`, `README.md`). `adapter.cwd` equals `evaluation.workspace.path`
(`/workspace/project`).

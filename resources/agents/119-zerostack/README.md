# zerostack ACP deployment

This unit builds [zerostack](https://github.com/gi-dellav/zerostack) (`gi-dellav/zerostack`,
revision `797dca9c`, crate `1.8.5`) from source with the `acp` cargo feature and runs its stdio
ACP server (`zerostack --acp`). ABB drives one ACP session per Case; follow-up inputs reuse that
session. No upstream file is modified.

This unit uses default model selection; no `[model]` declaration is needed. ABB passes the
resolved configuration through `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL`, and the runtime admits the `POST <selected-base>/chat/completions` route.

## Source and image

The upstream repository has a Git submodule (`tap`, a Homebrew tap), and ABB's Git source mode
rejects submodules. The unit therefore uses `source.method = "install"`: `install/` (the
launcher) is copied into `agent/`, and the Dockerfile's builder stage fetches exactly the pinned
commit (`git fetch --depth 1 origin <sha>`, checked with `git rev-parse`) without submodules,
which are not build inputs. It then runs `cargo build --locked --release --features acp`
(`rust-toolchain.toml` pins Rust 1.96.0; `.cargo/config.toml` selects mold).

The runtime stage is `debian:bookworm-slim` with `python3` for the ABB worker and `bash`/`git`
for zerostack's terminal tools. The PEP 668 `EXTERNALLY-MANAGED` marker is removed because ABB's
SDK overlay runs `python -m pip --isolated install`, which ignores `PIP_BREAK_SYSTEM_PACKAGES`.

## Launcher (`install/abb-acp-launch.py`)

zerostack reads its provider from `ZS_CONFIG_DIR/config.toml` (`docs/CONFIG.md`,
`custom_providers`). The launcher validates the three model variables, points `HOME`,
`ZS_CONFIG_DIR` and `ZS_DATA_DIR` at a disposable directory per Case and writes:

```toml
provider = "abb"
auto-update-prompts = false
auto-update-themes = false

[custom_providers.abb]
provider_type = "openai"
base_url = "<selected base>"
api_key_env = "ABB_AGENT_MODEL_API_KEY"
api_style = "completions"
model = "<model>"
```

The key stays in the environment and is never written to disk. The auto-update switches are off
so no interactive `y/N` prompt can read stdin (the ACP channel). It then execs
`zerostack --acp --provider abb --model <model>`. In ACP mode zerostack auto-approves its own
tool calls; the permission mode keeps the upstream default.

## Workspace fixture

`evaluation/fixture/` contains `RELEASE_NOTES.md` (Markdown with trailing-space hard line breaks)
and `counter.txt`. `adapter.cwd` equals `evaluation.workspace.path` (`/workspace/project`).

# Jan in ABB

This unit builds the pinned upstream headless `jan` CLI and uses its native ACP
stdio implementation. Upstream source remains in `agent/`; integration files live
beside it. ABB stages `.abb-runtime` and dependency overlays during evaluation, so
run the ABB command below instead of building the unstaged directory directly.

## Docker host platforms

One Linux Dockerfile is shared across these hosts:

| Host | Docker configuration | Container architecture |
| --- | --- | --- |
| Windows x86-64 | Docker Desktop using Linux containers / WSL 2 | `linux/amd64` |
| Linux x86-64 | Docker Engine or Docker Desktop | `linux/amd64` |
| Intel macOS | Docker Desktop | `linux/amd64` |
| Apple Silicon macOS / Linux ARM64 | Native ARM64 builder, or Docker Desktop emulation | `linux/arm64`, or emulated `linux/amd64` |

The Dockerfile uses Debian packages and Rust's detected Linux architecture; it
contains no Windows drive paths or macOS binaries. It is not a Windows-container
image.
For Apple Silicon, an explicitly selected `linux/amd64` image can use Docker
Desktop's emulation, which is slower for Rust compilation. Use a separate results
directory and check the actual image architecture when switching architectures.
See [Docker multi-platform documentation](https://docs.docker.com/build/building/multi-platform/).

## Greeting smoke run

Run from the ABB repository root, with its Python environment activated and the
shared model credentials configured. Shared ACP interception must be set to
`replace` in `agentbench/runtime/interception/policy.py`.

Windows PowerShell:

```powershell
$env:JAN_EXPERIMENTAL_ACP = '1'
python -m agentbench evaluate jan --sdk native --case-file resources/agents/146-jan/smoke/hello.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/jan-hello
```

macOS / Linux:

```sh
export JAN_EXPERIMENTAL_ACP=1
python -m agentbench evaluate jan --sdk native --case-file resources/agents/146-jan/smoke/hello.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/jan-hello
```

To select AMD64 emulation on an ARM64 Docker Desktop host, set
`DOCKER_DEFAULT_PLATFORM=linux/amd64` before building and running. Host paths and
shell syntax are handled outside the image; the Dockerfile stays the same.

## Native build corrections

The headless crate requires `--no-default-features --features cli`. Its
`.cargo/config.toml` redirects output to `../target`, so the installation source
from `src-tauri/jan-cli` is `../target/release/jan`.

The image also provides `python` in `/opt/venv` and installs the Python worker's
OpenTelemetry, JSON Schema and dotenv dependencies. These are image-local
dependencies, separate from the host's ABB Python environment.

`bootstrap/launch.py` writes the disposable container user's `~/.jan/config.toml`
from runtime-owned `ABB_AGENT_MODEL`, `ABB_AGENT_MODEL_BASE_URL` and
`ABB_AGENT_MODEL_API_KEY`, then replaces itself with the real `jan acp` process.
No model name, provider endpoint or provider secret is baked into the image.
The native provider uses the OpenAI-compatible chat-completions protocol; ABB's
shared ACP policy still controls `replace` versus `observe`. Jan's upstream
prompts, tools and ACP implementation are unchanged.

An image build alone does not establish successful ACP execution. Acceptance
requires the greeting to succeed, a real model reply, recorded `replace` model
requests, and the resulting trajectory; partial evidence must be reported.

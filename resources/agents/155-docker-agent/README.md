# docker-agent in ABB

This integration builds the pinned upstream source and launches its native
`docker-agent serve acp` server over stdio. The image derives its agent file from
the upstream built-in agent, preserving its native instructions and tools.

## Integration configuration

- The Go builder and Python runtime both use Debian Bookworm, avoiding an
  Alpine/musl versus Debian/glibc mismatch for CGO dependencies. The upstream Linux
  `no_audio` build tag is retained; CGO is not disabled.
- Python worker dependencies include OpenTelemetry, JSON Schema and dotenv.
  The image build checks both their imports and the native ACP command's help.
- The image copies `pkg/config/sources/builtin-agents/default.yaml` from the pinned
  source. `bootstrap/build_config.py` replaces only `models.smart` with the settings
  in `bootstrap/config.yaml`. The native ACP command receives the resulting file.
  The upstream loader expands `ABB_AGENT_MODEL` and `ABB_AGENT_MODEL_BASE_URL`, and
  reads the credential through `token_key: ABB_AGENT_MODEL_API_KEY`. A user-level
  `default_model` would not replace this built-in `first_available` selector.
- `provider: openai` selects the OpenAI-compatible client protocol, not a pinned
  endpoint or model vendor. `provider_opts.api_type: openai_chatcompletions`
  selects the protocol used by ABB's shared ACP route.
- Shared `observe`/`replace` selection remains in ABB's existing
  `agentbench/runtime/interception/policy.py`. No actual credential is stored in
  the image, and no upstream source modification is required.

## Docker hosts and greeting

Use the same Linux Dockerfile on Windows with Docker Desktop Linux containers,
macOS with Docker Desktop, or Linux with Docker Engine/Desktop. The base images
select the Linux CPU architecture of the builder. On an ARM64 host,
`DOCKER_DEFAULT_PLATFORM=linux/amd64` can select AMD64 emulation instead.

From the ABB repository root, activate its Python environment and configure the
shared model credentials. Run this command in PowerShell or a macOS/Linux shell:

```sh
python -m agentbench evaluate docker-agent --sdk native --case-file resources/agents/155-docker-agent/smoke/hello.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/docker-agent-hello
```

ABB stages `.abb-runtime` and its dependency overlays; use the ABB command rather
than building the unstaged agent directory directly. Runtime artifacts record
execution status, actual model traffic and trajectory coverage separately.

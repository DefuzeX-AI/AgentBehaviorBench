# Hercules in ABB

This unit wraps the pinned upstream `SingleCommandInputRunner`; the native
LangGraph planner, prompts and tools remain unchanged.

## Run on Windows, macOS or Linux

Use Docker with Linux containers (Docker Desktop on Windows/macOS, or Docker
Engine/Desktop on Linux). Activate the ABB Python environment and run from the
ABB repository root:

```sh
python -m agentbench evaluate testzeus-hercules --sdk native --case-file resources/agents/166-testzeus-hercules/smoke-case.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/hercules-smoke
```

The same Dockerfile uses the platform selected by Docker; it has no host drive
paths or fixed CPU architecture. Native dependencies come from the upstream UV
lock. ABB prepares `.abb-runtime` as part of the build. Chromium, its system
libraries and the native pinned uBlock archive are installed at build time.
Runtime project files and caches are writable by the unprivileged container user.

## Model interception

`agent.toml` declares the native OpenAI Chat Completions route and
`LLM_MODEL_API_KEY` as an interceptor-managed credential. In `replace` mode ABB
injects a placeholder into the agent and supplies the real replacement provider
credentials only to the interceptor. Do not add the native key to
`runtime.secret_env_keys` for this workflow.

The source-side defaults (`gpt-4o`, OpenAI's API endpoint) identify the native
request format; ABB chooses the actual replacement model using its shared model
configuration. Native prompt and tool contents are preserved. The mode belongs
to ABB's shared interception policy, not a per-agent hardcoded switch.

Only the Chromium engine is installed. Browser/API test destinations need their
own scoped `llm_interception.tool_routes`; the greeting case requires no external
tool routes. uBlock is cached from the exact version selected in upstream code,
so normal startup does not need GitHub download access.

Inspect the resulting `trajectory.json` and network evidence for a successful
input, a real native reply and model requests recorded with `mode: replace`.
A trajectory file alone is not proof of successful execution.

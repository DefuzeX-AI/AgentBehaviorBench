# AutoDev Xiuper

This unit runs the published `@xiuper/cli@1.0.2` native `xiuper acp` server with `@xiuper/mpp-core@1.0.2`. Both npm packages identify source revision `47f9aab58f023dc777fbb5f3c71c539fa0a40a82` in `phodal/auto-dev`. `install/package-lock.json` pins every installed package and its integrity hash. The published Kotlin JavaScript artifacts are included; no local Kotlin checkout or generated build directory is required.

## Configuration and source

`agent.toml` declares install-mode source. ABB restores ignored `agent/package.json` and `agent/package-lock.json` from tracked `install/` before constructing the image. The Dockerfile installs official packages with `npm ci --ignore-scripts` and invokes their unchanged ACP command. Do not commit the generated `agent/` directory.

The outer launcher maps `ABB_AGENT_MODEL_API_KEY`, `ABB_AGENT_MODEL_BASE_URL` and `ABB_AGENT_MODEL` into Xiuper's native `custom-openai-base` configuration. It does not pin a provider or invent a model catalog. The native client appends `chat/completions` to the selected base URL. The credential is written at container startup into a mode-0600 config file under a private temporary home outside the Case workspace; it is never embedded in the image or command line. Node trusts ABB's interception CA via `NODE_EXTRA_CA_CERTS`.

No MCP server or external tool service is configured. Native tool implementations and the coding loop remain unchanged. The native ACP version has asynchronous permission notification and incomplete cancellation propagation: a client denial or cancellation must not be assumed to prevent further tool execution. See `requirement.md` for the deployed evaluation boundary. The native ACP renderer also reconstructs some tool arguments by splitting a text parameter string on whitespace (`AcpAgentServer.js:244-254`); `rawInput` can therefore omit argument content. Preserve raw tool outputs and model traffic alongside ACP events rather than treating the displayed argument object as complete.

## Local execution

Use the repository Python environment and configured model credentials, with Docker running. The shared registry retains `adapting` and disabled status. For a manual evaluation, create an uncommitted `resources/autodev-smoke.toml` with this explicit selection:

```toml
schema_version = "defuzex-bench.registry.v1"
[[agents]]
agent_id = "autodev"
path = "resources/agents/127-autodev"
enabled = true
status = "adapting"
framework = "acp"
case = 1
step = 1
```

Run the supplied fixed-input execution check:

```sh
agentbench evaluate autodev --registry resources/autodev-smoke.toml --sdk native \
  --case-file resources/agents/127-autodev/validation/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --no-view
```

This calls the real Agent and model but does not request a Judge. For the standard Local Smoke workflow, let the local SDK generate its own Case and Judge:

```sh
agentbench evaluate autodev --registry resources/autodev-smoke.toml \
  --sdk local --cases 1 --max-steps 1 --case-retries 0 --no-view
```

For official evaluation, select `--sdk kuma` instead; that invokes the official service and may consume KUMA credits. Keep generation, execution, host evidence acceptance and Judge verdict separate. A received report is not final project acceptance, and this unit does not claim any confirmed GT.

## Offline checks

```sh
python -m pytest -q tests/test_issue455.py
```

The focused test restores a clean install-mode unit, validates its configuration and parses the Agent Profile with the installed official KUMA SDK. Online catalog validation must use a fresh SDK onboarding context. No credential is required by these focused tests.

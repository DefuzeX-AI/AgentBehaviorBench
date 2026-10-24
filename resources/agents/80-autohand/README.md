# Autohand native ACP integration

Onboarding task: [#508](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/508).

The unit installs the official `autohand-cli@0.9.8` npm distribution using the
committed `install/package-lock.json`. npm's `gitHead` and upstream tag `v0.9.8`
both identify `55f07f8112d3d53739c4c45d7c19d73772e645d7`. The source tag's
`package.json` still says `0.8.2`; the published npm version is `0.9.8`.
`distribution.json` records npm provenance and integrity. Upstream is Apache-2.0.

## Native execution

`bootstrap/launch.py` starts the package's unmodified `autohand --acp` entrypoint.
It writes ABB's resolved model, endpoint and credential into a fresh private
Autohand configuration, then replaces itself with the native process. The native
Agent loop, file/command tools, ACP session handling and permission bridge remain
unchanged. There is no protocol relay or patched tool implementation.

The launcher maps ABB's OpenRouter, DeepSeek and GLM selection to Autohand's
native `openrouter`, `deepseek` and `zai` providers. Missing configuration and
unsupported providers fail without fallback. Credentials are not CLI arguments;
each Case has a separate home and a mode-0600 configuration. Native Interactive
permissions remain active and ABB uses `allow_once`. Optional upstream telemetry,
cloud trace sync, crash reporting and version pings are disabled.

The Docker image uses Node.js 24 and retains the package's normal production
dependencies. After `npm ci`, it explicitly runs the pinned packages' own
node-pty, node-llama-cpp and Autohand lifecycle scripts because npm's approval
policy may defer them. It also provides Python, Bash, Git and ripgrep.
No GPU or local model weights are required for the cloud-model deployment.

## Run

Follow [model selection](../../../docs/Model-Selection.md) and configure the
selected provider outside Git. For example:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
```

The committed registry entry stays disabled/adapting. Enable it in a local
registry and run the published smoke Case:

```bash
agentbench evaluate autohand --sdk local --registry resources/registry.toml \
  --case-file docs/validation/issue508-autohand/case.json \
  --cases 1 --max-steps 2 --case-retries 0 --no-view
```

The ABB host controller must have permission to remove the container-owned
workspace at teardown. The validated run used host root in WSL; the Agent and
SDK containers retained UID 10001. Running the controller as host UID 1000
completed both Agent inputs but failed during recursive `.autohand` cleanup.
This unit does not fix that generic ABB ownership issue or relax directory
permissions. An ordinary-user host with a different UID is not demonstrated
working; independent acceptance must account for this prerequisite.

The two-turn Case creates and executes `total.py`, then modifies the same file,
reads it, executes it again and checks retained conversation context. Local
Smoke uses the selected model and Local Judge; it does not use KUMA backend
Credit or establish a GT defect. Only DeepSeek is selected for this acceptance;
static provider mapping does not demonstrate every provider/model combination.

See [acceptance records](../../../docs/validation/issue508-autohand/README.md)
for the exact execution outcome and the limits of the public evidence package.

## Deployment limits

Cases begin with an empty Linux workspace. External MCP servers, browser binaries,
cloud/service credentials, local model weights and search keys are not provisioned.
Runtime network access is limited to the selected model route; other native tools
retain their registration but may report unavailable prerequisites or refused
network access. These limits are described in `requirement.md`. This deployment
uses text ACP and does not provide external desktop control or cross-Case state.

Pinned upstream references:

- [Native ACP](https://github.com/autohandai/code-cli/blob/55f07f8112d3d53739c4c45d7c19d73772e645d7/docs/guides/ACP.md)
- [Providers](https://github.com/autohandai/code-cli/blob/55f07f8112d3d53739c4c45d7c19d73772e645d7/docs/providers.md)
- [Native session initialization](https://github.com/autohandai/code-cli/blob/55f07f8112d3d53739c4c45d7c19d73772e645d7/src/modes/acp/adapter.ts)

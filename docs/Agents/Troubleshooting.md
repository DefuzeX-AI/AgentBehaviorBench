# Agent Troubleshooting

Search this page by the error text you see in the terminal or result artifact.

## `AgentInvocationError`

This is a wrapper. Open the JSON artifact and find the inner error:

```powershell
python -m agentbench view results\certify-<agent-id>-<timestamp>.json
```

Common inner errors are below.

## `FileNotFoundError` under `site-packages`

Example:

```text
FileNotFoundError: /usr/local/lib/python3.11/config/agentbench.yaml
```

Cause: code derived project root from `Path(__file__)` after `pip install .`.
Fix: use explicit env-driven paths such as `MY_AGENT_CONFIG_DIR=/opt/agent/config`
or `SWE_AGENT_CONFIG_ROOT=/opt/agent`.

## Static Fixture Missing

Example:

```text
FileNotFoundError: .../site-packages/benchmark_mocks/fixtures/buggy_repo_template
```

Cause: fixture exists in source but was not included in the installed wheel.
Fix: add package-data entries or copy the fixture under `/opt/agent`, then add a
test that verifies every declared fixture file exists.

## Tool Exists But Cannot Execute

Example:

```text
RuntimeError: Tool str_replace_editor is not available in the container.
/bin/bash: ... Permission denied
```

Check:

```bash
mount | grep agentbench-tools
```

Cause: executable tool was uploaded to a `noexec` mount. A file can be `755` and
still fail if the mount is `noexec`.

Fix: upload executable tools to `/run/agentbench-tools`, not `/tmp`.

## No native Agent caller configured

Container startup and invocation are separate. Use the native service API or
supply `RuntimeFactory(container_caller=...)` for legacy evaluation. Do not
change the Agent's log output to satisfy an invocation protocol.

## Agent Works Locally But Not In Docker

Likely causes:

- editable install hid missing package metadata;
- `.env` existed locally but not in container;
- package data was not included;
- Docker build context excluded required files;
- runtime wrote under `/root` or read-only paths;
- code tried to execute tools from `/tmp`.

Reproduce inside the image, not in the host Python environment.

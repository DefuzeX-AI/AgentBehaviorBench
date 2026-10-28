# AgentCrew integration

This unit targets AgentCrew 0.23.0 at the commit in `agent.toml`. ABB restores
the ignored `agent/` source from that pinned Git revision before execution.
Integration inputs live outside the upstream source.

`bindings/launch.py` runs the native ACP CLI with the upstream Engineer prompt
and default tool selection. The launcher maps ABB's runtime-selected model to
a native OpenAI-compatible custom provider and registers its model so auxiliary
memory, code-analysis and tool-result-summary clients use the same selection.
The native CLI resolves this provider through `AGENTCREW_PROVIDER`; its
`--provider` option accepts only built-in provider names.

Native configuration containing the credential is generated in a private
temporary directory with a mode-0600 configuration file. Normal shutdown and
SIGTERM remove this directory. Container removal also removes ephemeral files
after forced termination. Credentials are never part of committed configuration
or command arguments. ACP uses a reserved output pipe; native stdout diagnostics
go to stderr. Upstream initialization, permissions and resource shutdown remain
in the native application.

The image installs the native production lock in a separate Python environment.
Requirements are exported from the frozen lock and installed with hash checking.
Build arguments `ABB_DEBIAN_MIRROR`, `ABB_DEBIAN_SECURITY_MIRROR` and
`ABB_PIP_INDEX_URL` allow regional mirrors without editing dependency inputs.
Probe download throughput from the Docker network before choosing an override.
ABB's worker/adapter overlays and the project's declared OpenTelemetry extra use
the image's system Python. Chromium and Node come from architecture-matched
Debian packages; parser and local embedding caches
are populated as the runtime user. The native Docker browser setting uses its
upstream `--no-sandbox` mode inside the container.

`requirement.md` describes the provisioned capabilities for local evaluation.
It has no KUMA strategy selection yet: fresh catalog selection and KUMA evaluation
remain separate work. Parser acceptance does not establish KUMA service readiness.
No Tavily, image/voice provider or external MCP server is configured. Browser
destinations remain subject to the run's egress policy.

The pinned native ACP terminal validator rejects Linux working directories.
It applies `os.path.abspath(working_dir).startswith(prohibited)` to a blacklist
containing `/`. This also rejects ordinary workspace paths after individual
permission approval. The launcher preserves this policy; it does not bypass
validation or substitute another execution tool. The Profile states this
limitation explicitly. See the upstream [ACP validator](https://github.com/saigontechnology/AgentCrew/blob/eaff35483b1fea0a856d9e1dd3ce85ace0cf9c04/AgentCrew/modules/acp/tools/terminal.py#L340)
and [prohibited paths](https://github.com/saigontechnology/AgentCrew/blob/eaff35483b1fea0a856d9e1dd3ce85ace0cf9c04/AgentCrew/modules/command_execution/constants.py#L63).

Static validation and source restoration do not demonstrate successful execution.
Retain ACP startup evidence separately from a real multi-turn Agent/SDK smoke
Case and Judge result. The unit must not be described as accepted until the
corresponding runtime artifacts exist.

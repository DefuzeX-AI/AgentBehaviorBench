# Decepticon native orchestrator integration

The binding calls `create_decepticon_agent()` without prompt/tool/middleware
replacements. The native forced-model deployment setting selects a source model
label and ABB replace chooses the actual model. Native OpenShell admission remains
in force; no approved scope or sandbox is invented to make a greeting pass.

The imported snapshot includes benchmark submodules, so source preparation is
bundled. Supply the pinned source and its submodules from source-manifest.json.
The Docker build only copies runtime packages, configuration and skills.
Docker Linux containers support Windows, macOS and Linux hosts.

`python -m agentbench evaluate decepticon --sdk native --case-file resources/agents/79-decepticon/smoke-case.json --cases 1 --max-steps 1 --no-view -y`

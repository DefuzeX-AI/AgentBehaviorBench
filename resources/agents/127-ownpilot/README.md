# OwnPilot native ACP integration

This unit acquires OwnPilot 0.8.3 at pinned Git revision
`568cf7eee2ec5fa82d66ffdb984e2202171bffce`. Source preparation restores the
ignored `agent/` tree and copies the additional ABB-owned provider descriptor
from `install/`; no upstream implementation is patched.

The image builds the upstream CLI and its workspace dependencies with the
upstream pnpm lockfile. The launcher initializes a private, non-root PostgreSQL
16 cluster on loopback for the Case, writes runtime-selected model settings
through native public repository/configuration exports, and starts the original
`acp-serve` command. The supervisor stops PostgreSQL after the native child exits
or on termination. Only console diagnostics are redirected to stderr; native
ACP stdout remains the protocol stream.

`ABB_AGENT_MODEL_BASE_URL`, `ABB_AGENT_MODEL`, and `ABB_AGENT_MODEL_API_KEY` come
from ABB model selection/interception. The additional native-format
`abb-runtime` provider uses the selected base URL without adding `/v1`, and the
native unknown-model budget defaults apply. No upstream provider descriptor,
tool group, permission decision, prompt or Agent loop is changed.

Native default groups expose files, calculations, personal data, memory, goals,
utilities and custom-tool management. Direct code execution is disabled by
upstream defaults. Native gateway approval decisions are not bridged into ACP
permission requests and may reject operations. No external tool credentials or
host Docker socket are supplied. See `requirement.md` for evaluation scope.

See [validation report](../../../docs/validation/issue489-ownpilot/README.md)
for measured execution, judgment and capture boundaries.

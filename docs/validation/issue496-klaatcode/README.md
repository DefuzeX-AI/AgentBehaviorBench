# Klaat Code integration acceptance (#496)

This is the first-stage integration test on 2026-10-25, not an official KUMA
evaluation or a Ground Truth finding. Upstream is pinned to
`b988be7cf6ffe7878e87ed3e720759e0f7247c33` (native package version 2.5.0), on ABB
`1061a09b94db5f35690691207a5423e5ca6eb814`.

## Observed result

One Case with two conversation turns completed through the native ACP loop:

1. Native `write_file` created `total.py` with [4, 7, 9]; `run_command` executed
   it and observed 20, with exit code 0.
2. Native `read_file`, `edit_file`, a fresh `read_file` and `run_command` changed
   the list to [4, 7, 9, 6] and observed 26, with exit code 0. The same native
   session recalled the conversation label.

Eight model requests and eight HTTP-200 responses were intercepted. Four native
permission requests received `allow_once`. Local Judge returned pass/high with
no issues or evidence gaps; the full CLI exited 0, and host trace validation
and workspace cleanup succeeded. This supports this specific integration Case,
not a claim of general behavioral correctness.

The controller ran as root in WSL to allow cleanup of container-owned workspace
files. The Agent and SDK containers remained nonroot UID 10001. This host
prerequisite is not a fix to ABB's generic cross-UID cleanup behavior.

## Configuration boundaries

The unit-local bootstrap calls the unchanged native AcpAgent and AcpConnection,
and sets its KlaatAIClient's existing custom endpoint after initialization.
The native ACP CLI does not expose the TUI's `/model` switch. This bootstrap
therefore accesses the pinned class's TypeScript-private `client` property;
future revisions need revalidation. Agent logic, prompts, tools and permission
handling are not patched. Eleven focused launcher checks and a real
network-disabled initialize/session handshake pass; all 615 restored native
Git blobs match upstream.

No Klaatu subscription credential is present. A noncredential marker satisfies
the native initialization presence check. Actual Chat Completions use ABB's
selected key/model through native `setCustomEndpoint`. Hosted Klaatu graph,
routing and web services remain unavailable. The Profile lists those limits.

The native client inserts `/v1` if the model base lacks a version suffix. ABB
authorizes an exact path, so use `DEEPSEEK_BASE_URL=https://api.deepseek.com/v1`.
The final launcher rejects an incompatible unversioned base before prompts.

Two earlier attempts completed initialization but failed their first input:
the native `/v1/chat/completions` path differed from ABB's authorized
`/chat/completions`, and egress denied the request before model inference.
An intermediate selected-host NO_PROXY experiment did not resolve it and was
removed. Both failed CLI records and original manifests are retained; neither
is called a successful run or an Agent behavior defect. The final acceptance
uses versioned native configuration, preserves the proxy environment and
retains actual model interception. No wildcard route or network bypass was added.

## Reproduce

Configure the selected provider credential privately using the ABB setup guide.
Use a temporary registry with just this unit enabled; the committed entry stays
disabled/adapting. On a Linux filesystem with the cleanup access above:

```bash
export ABB_MODEL_PROVIDER=deepseek
export DEEPSEEK_MODEL=deepseek-flash
export DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
export ABB_LOCAL_JUDGE_MAX_CHARS=1200000
agentbench evaluate klaatcode --sdk local --registry /path/to/runtime-registry.toml \
  --case-file docs/validation/issue496-klaatcode/smoke-case.json \
  --cases 1 --max-steps 2 --case-retries 0 --timeout 600 --no-view -y
```

The larger local Judge character guard admits complete evidence; it does not
truncate evidence or change the Judge prompt/validator. Agent and local Judge
model API calls can cost money; this run used no official KUMA Case/Judge call
or KUMA Credit.

## Evidence scope

`execution-manifest.json`, `host-run.json`, `judge-report.json`, input contracts,
ACP summaries and CLI results are bounded copies without rewriting. The
final-response, model-traffic and tool-event extracts are labeled separately;
full native results, model payloads/reasoning and raw traces remain local.
`acceptance-summary.json` indexes run identities and SHA-256 hashes, rather than
replacing SDK evidence. Known credentials were checked against the public files.
The unit-local configuration and bootstrap files are described in the unit README.

GT exploration has not started. It follows #496's merge/credit procedure after
maintainer review of this integration.

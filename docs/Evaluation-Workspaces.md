# Evaluation workspaces and file evidence

An Agent can opt into an isolated evaluation workspace in its outer `agent.toml`:

```toml
[evaluation.workspace]
path = "/home/agent/workspace"
initial_state = "empty"

[evaluation.file_evidence]
track_files = true
upload_diff = true
export_changed_files = true
```

ACP `adapter.cwd` must equal this path. Programs and dependencies stay under
`/opt/agent`; the workspace cannot mask that directory or an entire home.
Existing units without these tables retain their original SDK repository and
file-tracking defaults. `ManifestOptions(evaluation=...)` supplies the same
explicit policy to programmatic onboarding and its SDK capability catalog.

For a prepared project, use `initial_state = "fixture"` and
`fixture = "evaluation/workspace"`, a directory in the outer Agent unit. Only
regular files and directories are admitted, with a 32 MiB / 10,000-file bound.
Links and `.git`/`.kuma` state are rejected. Generation and each Case attempt
copy the same initial state; turns within a Case share their workspace. KUMA's
`.gitignore` exclusion is prepared before generation.

A Case collection retains the initial workspace identity and content digest.
The prepared Case carries its environment fingerprint through Suite persistence
and recovery. Execution rejects a changed environment or an older Case lacking
this contract before invoking the Agent. The signed SDK Case bytes and public
Case identity remain unchanged. Generate new Cases when adopting this policy.
An environment match does not prove that every natural-language Case has valid
prerequisites: the pinned official Case contract does not declare structured
required files. Profiles for empty workspaces must require self-contained tasks.

KUMA captures each Input's baseline and final snapshots and prepares the file
diff in its actual Submission. `upload_diff` uses the SDK's capability negotiation
and privacy policy. ABB saves `inputs/NNNN/file-evidence.json` beside the original
Submission, exposing separate snapshot/diff statuses and omission reasons.
The Viewer Files / Diff filter supports text search of these artifacts.

Before container cleanup, ABB uses the SDK Snapshotter to export bounded changed
text files under `evaluation/workspace-files/` and writes
`workspace-artifacts.json`. This is a final changed-file export, not a complete
filesystem backup. Deleted files, binary/oversized content, links, and sensitive
content have explicit statuses. The raw writable workspace is temporary and is
removed after the container closes; only the separate `.kuma` recovery ledger
and sanitized evidence remain. Temporary workspace and ledger must use the same
Docker host filesystem share because KUMA rejects ledger mount/device escapes.

MiniMax's optional content-review service uses managed-login credentials, separate
from its model API key. `runtime.optional_secret_env_keys = ["MAVIS_ACCESS_TOKEN"]`
forwards the native service's supported access token only when explicitly present
in the execution environment. Absence does not prevent BYOK model execution.
The native title/review behavior stays enabled; a 401 remains an optional-service
failure, never a synthesized pass. No model API key is substituted for this token.

`llm_interception.observation_headers` can retain explicitly named non-credential
native session/turn/request metadata without modifying the original headers.
These are observations, not authorization or ABB Case/Input identities. MiniMax
uses its existing `X-Mavis-Session-Id`; unmatched background traffic can therefore
remain session-only. Exact Input assignment still requires a validated native
response ID or emitted tool relation.

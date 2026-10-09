# Local Agent source directories

[Back to README](../README.md) · [Add an Agent](How%20To%20Add%20Agent.md)

ABB tracks the outer integration files in `resources/agents/NN-name/`: manifests,
bindings, Dockerfiles, installation inputs, evaluation profiles, fixtures, source
provenance and Ground Truth. Every inner `agent/` directory is local source or
runtime material and is excluded by `/resources/agents/*/agent/` in `.gitignore`.
A fresh checkout contains no files in those directories. Do not force-add them.

## Preparing source

The existing `run`, `evaluate` and `certify` flows prepare selected Agent sources
before opening an evaluation SDK session. Registry discovery reads configuration
without downloading source and can list units whose local source is absent.

- `source.method = "git"` fetches the complete commit SHA already recorded in
  `agent.toml`, caches it under `cache/sources/`, and restores the ignored `agent/`.
  Git and network access are required on the first cache miss. It never substitutes
  a newer branch revision. Existing unmanaged local source is reused without a fetch.
- `source.method = "install"` copies tracked `install/` inputs into the ignored
  `agent/`. Package installation still belongs to the Agent Dockerfile.
- `source.method = "bundled"` means manually supplied local source. It no longer
  implies that ABB commits that source. Copy the matching source into `agent/`
  before execution. A missing directory fails during source preparation.

Existing local edits are not overwritten. Direct Docker builds and low-level SDK
calls must have source prepared first. See [runtime source preparation](../agentbench/runtime/source/README.md)
for cache validation, ownership and failure behavior.

## Manual prerequisites

These registered integrations retain `method = "bundled"` because the current
Git acquisition implementation cannot reproduce their source:

| Unit | Required local material |
| --- | --- |
| `01-folder-mover-agent` | The original local source snapshot matching the recorded SHA-256 content digest; the recorded Windows path is provenance, not a portable download URL. |
| `13-claude-agent-acp` | The selected upstream checkout, including its documentation link handling. The pinned source contains a symbolic link; automatic Git extraction rejects symbolic links. |
| `41-biomedical-aiq-research-agent` | The selected upstream checkout and required data assets. Its dataset ZIP files are Git LFS objects; automatic Git extraction does not materialize LFS. |

For GitHub sources, the repository and exact commit are recorded in each unit's
`agent.toml` and `source-manifest.json`. Supply the matching source tree under that
unit's `agent/`, without copying another Git repository's `.git` metadata. Obtain
LFS datasets from the upstream project; pointer files are not the datasets. At the
migration revision, the Biomedical AI-Q LFS objects were unavailable from ABB's
LFS server, so an old ABB checkout alone cannot supply those data assets.

The previously committed source snapshots remain in Git history at
`e2c081ff52c71593e4cd49dc5dec7c003e7e9109`; this change removes them from the new
checkout tree and does not rewrite history. Registry readiness records describe
previous certification and do not certify a new download or manual restoration.

## Contributing an integration

Import or restore source locally to inspect and test its actual behavior. Commit
only the outer integration, installation inputs, provenance and Ground Truth.
Choose pinned Git acquisition when its source features are supported; otherwise
document manual prerequisites. Keep Agent behavior in its own upstream project.

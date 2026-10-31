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
  If the unit also has `install/`, preflight copies its tracked integration inputs
  into `agent/` after source preparation, including when reusing existing source.
  Missing copies are repaired; differing existing files are never overwritten.
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
| `10-claude-agent-acp` | The selected upstream checkout, including its documentation link handling. The pinned source contains a symbolic link; automatic Git extraction rejects symbolic links. |
| `37-biomedical-aiq-research-agent` | The selected upstream checkout and required data assets. Its dataset ZIP files are Git LFS objects; automatic Git extraction does not materialize LFS. |
| `86-fast-agent` | The pinned checkout with its optional, uninitialized skills submodule; follow the [unit instructions](../resources/agents/86-fast-agent/README.md#source-preparation). |
| `112-alphastream` | The pinned checkout without the unavailable, unused TradingAgents submodule; follow the [unit instructions](../resources/agents/112-alphastream/README.md#restoring-source). |
| `124-synergy` | The pinned checkout with its internal symbolic link preserved on a Linux filesystem; follow the [unit instructions](../resources/agents/124-synergy/README.md#manual-source-prerequisite). |
| `132-whip` | The pinned checkout prepared with the unit helper to materialize its internal directory link; follow the [unit instructions](../resources/agents/132-whip/README.md#manual-source-prerequisite). |

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

## ABB-owned LangGraph descriptors

Keep ABB-added `abb-langgraph.json` files in each unit's outer `install/`, not only
in its ignored `agent/`. Git source preparation copies them into the source root
before SDK startup and Docker staging. Continue editing the tracked `install/`
file; if its generated copy differs, move that copy aside before preparing again.
This mechanism adds integration inputs without replacing upstream files.

The 13 descriptors removed with inner source in `390e5b6d` were recovered verbatim
from that commit's parent into `install/`. This includes Multi-Agent CAD: its local
copy survived in one checkout, but a fresh upstream export also needs the tracked
descriptor. Package-only units retain their existing `method = "install"` behavior.

## Contributing an integration

Import or restore source locally to inspect and test its actual behavior. Commit
only the outer integration, installation inputs, provenance and Ground Truth.
Choose pinned Git acquisition when its source features are supported; otherwise
document manual prerequisites. Keep Agent behavior in its own upstream project.

## Shared installation inputs and onboarding checks

All acquisition methods apply `install/` into `agent/` before execution, including
`bundled` and manifests that omit `source.method`. Bundled units still need their
manual source first; installation inputs alone do not replace it. An absent
`install/` is optional for Git/bundled and required for install mode. A present
empty directory, unsafe path or different destination file fails preparation.
Missing copies are repaired under the same per-unit lock used for Git restoration.

`agent add -b` prepares existing installation inputs before collecting generation
evidence and rechecks them before registration. ABB-owned graph descriptors use
`abb-*.json` and must have their durable counterpart under outer `install/`.
Native upstream descriptors keep their native paths; bindings stay outside source.
The generator uses pinned Git acquisition for supported GitHub imports, preserves
explicit acquisition policy, and uses manual bundled source for local imports or
unsupported submodule, symlink and LFS layouts. See the add-agent guide for review
and clean-source verification; static checks do not prove successful execution.

## Refreshing the Agent inventory

The five localized Agent inventories are generated from `resources/registry.toml`
and the registered units' `agent.toml` files. After changing registrations, source
revisions or acquisition methods, regenerate and verify them from the repository root:

```bash
python scripts/update_agent_docs.py
python scripts/update_agent_docs.py --check
```

The inventory counts registry entries, not directory-number ranges. It includes
disabled and adapting integrations; operational state and Case budgets remain in
the registry. Historical validation reports retain their original observations.

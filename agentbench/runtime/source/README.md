# Runtime source preparation

`onboarding/source.py` imports a new Agent unit for `agent add`. This package
instead restores a registered Docker Agent's pinned source before execution.
It never creates registrations or regenerates integration configuration.

## Enable pinned Git source

In a source-based unit's `agent.toml`, add an explicit acquisition method:

```toml
[source]
method = "git"
repository = "https://github.com/guy-hartstein/company-research-agent"
revision = "c7142035a1cd413e34ad0595dbe9b5ca8b0308e8"
```

This requires `[runtime] type = "docker"` and `[build] context = "."`.
Use a complete commit SHA, not a branch or tag. Existing `run`, `evaluate` and `certify`
commands need no new flags. Registry discovery validates the declaration but
does not download anything; a Git unit may have no local `agent/` directory.
The common SuiteRunner checks selected units before opening the SDK session.
KUMA and Docker staging only copy files; neither performs source downloads.

Missing `method`, or `method = "bundled"`, keeps existing behavior: copy local
files. Package-based units use `method = "install"`: their tracked inputs live
in `install/`, and preflight copies these into the ignored `agent/` directory.
Their repository/revision fields describe provenance and do not trigger a clone.
For example, OpenHands keeps requirements.txt in install/; OpenClaw keeps
package.json and package-lock.json there. Dockerfiles still consume agent/.

Edit install/, not its generated agent/ copy. If the copy differs, preparation
fails without overwriting it; move agent/ aside and rerun to regenerate. Missing
files are repaired automatically. Missing/empty install/ is a configuration error.
The root .gitignore excludes resources/agents/*/agent/. Already tracked legacy
source remains tracked; it is not removed as part of the package-unit migration.

## Preparation and ownership

1. Check the manifest, Docker configuration and requirement document. Missing
   integration files are errors; downloading upstream source cannot restore them.
2. Check local source. Preserve existing unmanaged local trees without network
   access. For ABB-restored trees, verify the saved per-file hashes and inventory.
3. If source is absent, empty, or has missing inventoried files, acquire a unit
   lock and a per-source cache lock under `<project>/cache/sources/`.
4. Fetch the declared commit, verify its identity, and export a ZIP archive. Publish
   only a complete archive with an atomic rename; reuse it on subsequent runs.
5. Extract and validate in a temporary directory. Restore the local `agent/`
   atomically when absent, or publish only missing files when partially present.
6. Recheck the restored inventory. Only then open SDK sessions and start Cases.

Existing files and agent.toml are never overwritten. ABB restores missing files
into the registered unit so later runs can reuse them. An edited file in an
ABB-restored tree stops preparation with an error instead of losing edits.
Unmanaged local trees have no trusted inventory: they are retained, but their
completeness and exact upstream version cannot be proven. Keep package-based
units in install mode; their manifests must not be replaced by a Git tree.
Changing revision on a managed unit requires moving its existing agent/ aside.

`config.py` validates policy, `git.py` acquires/exports the commit, `cache.py`
coordinates archive publication, `inventory.py` validates source files, and
`preparation.py` owns preflight/restoration. SuiteRunner calls the shared entry
point before `runner_factory.open_suite`, SDK validation or Case generation.
Direct low-level runtime/SDK callers must prepare the unit themselves.

## Limits and failures

The host needs Git and network access on a cache miss. Acquisition has a
300-second budget and honors caller cancellation/deadlines. Failed downloads
are not reusable; no fallback to the latest branch is allowed. Cache ZIP CRCs
and commit metadata are checked on reuse; a corrupt archive reports its path
for removal and retry.

Version one rejects Git submodules and source symlinks instead of constructing
an incomplete or escaping tree. Git LFS materialization is not supported.
Use bundled source for these repositories. Package installation stays in each
Agent's Dockerfile. No Agent container or paid model call is needed for the
local regression tests:

```powershell
python -m pytest -q tests/test_runtime_source.py
```

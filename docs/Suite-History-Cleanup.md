# Saved Suite cleanup protection

`agentbench clean --dry-run` lists both archivable history and retained entries.
`agentbench clean` moves only unreferenced top-level entries under `results/`
into the recoverable `cache/history-trash/` archive.

A persisted Suite protects its own directory and every artifact referenced by
its event history, including failed, pending and superseded Attempts. Protection
also applies after a Suite completes. When a referenced Attempt is inside
`results/observe/`, the entire `observe/` entry stays at its original path. Moving
its parent would break the absolute paths needed by recovery and report viewing.
This conservative rule can retain unreferenced sibling artifacts as well.

Fresh and reused Suites register their location under
`cache/suite-references/`. This index allows a Suite in a custom output directory
to protect Attempts stored in the default `results/` tree. It stores only Suite
identity and path. Suite publication and cleanup use a short process lock so
cleanup cannot move an entry between Suite creation and index registration.
Cleanup rechecks the references after the preview, before moving any history.

Malformed or missing indexed Suite state stops cleanup. A missing file does not
prove that its referenced Attempts are safe to move. The command reports the
validation error and leaves history in place; restore or inspect the affected
Suite before trying again.

Legacy standalone result files without a durable Suite plan remain readable and
recoverably archivable. Agent-generated text is never interpreted as a cleanup
reference. This feature does not provide permanent deletion or retirement of a
saved Suite. Stop active runs and viewers before cleaning legacy history.

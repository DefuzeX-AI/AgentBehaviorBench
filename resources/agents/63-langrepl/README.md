# langrepl runtime preparation

This directory prepares the Python 3.13 runtime for midodimori/langrepl at
`b0d3780878441ee33d10062b040e5415c8b5da59` (package 1.12.1, MIT).
The pinned source must be materialized under the ignored `agent/` directory
before building; `source-manifest.json` records its provenance. Upstream source
is not committed or modified.

The Dockerfile exports production requirements from the frozen upstream
`uv.lock`, installs them with hash verification, installs the native package
without resolving dependencies again, and runs `pip check`. The lock's yanked
NumPy 2.4.0 is preserved. Git, ripgrep, fd, tree, bubblewrap and CA certificates
are installed for the native tool environment. Execution uses a non-root user
and a writable `/workspace/langrepl` directory.

## Sandbox findings

The locked package provides `pyseccomp`, while upstream's bubblewrap backend
imports `seccomp`. Direct `pyseccomp` import therefore does not establish native
syscall-filter support. The tested standard Docker policy also denies
bubblewrap namespace creation. Native optional sandboxing is disabled by
default and remains disabled; no privileged Docker configuration or upstream
patch is introduced.

This runtime preparation alone does not establish graph invocation, ABB
telemetry compatibility, or an evaluation result.

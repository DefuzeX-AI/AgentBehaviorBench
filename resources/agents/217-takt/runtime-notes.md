# Native TAKT deployment

The Dockerfile runs the original build and `takt install opencode`, then checks
the original managed-provider integrity state. A global OpenCode executable by
itself does not satisfy TAKT's managed SDK/runtime requirement.

The image runs Linux containers and uses architecture-neutral build commands.
Windows and macOS hosts require a Linux Docker engine, such as Docker Desktop.
Provider/model configuration comes from ABB's runtime model selection; the
upstream assistant, workflow logic and permission boundaries remain intact.

## Windows source staging

TAKT contains unusually long upstream fixture paths. The successful recovery run
used an extended-length absolute registry path and a short, ordinary temporary
directory (`C:\bt`) for that evaluation process's `TEMP` and `TMP`. It did not
change machine-wide Windows settings or remove upstream fixtures.

Use an owned short directory for those process-local variables. Do not put the
`\\?\` prefix on `TEMP` or `TMP`: Docker rejects extended-length Windows paths
when those temporary files become bind mounts. The registry path may use the
prefix because it is read by the host, not bound directly into the container.

The recovery directory was removed after the completed run. Create and verify a
new owned temporary directory before repeating that Windows launch arrangement,
then clean it only after the evaluation and its containers have stopped. Linux
and macOS do not require these Windows path settings.

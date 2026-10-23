# Worker image reuse

`worker_build_context` stages the Agent and the shared ABB execution package.
It excludes the host-only top-level `cli`, `onboarding`, and `__main__.py` from
the injected package. Editing CLI presentation or onboarding prompts therefore
does not produce a new worker image. Shared SDK, harness and observation code
is retained because container workers also import it.

`DockerImageBuilder` identifies images by file paths relative to the staged
context and file contents, plus the selected Dockerfile. Temporary directory
names and modification times are not part of the fingerprint. An existing
image with the matching full fingerprint label is reused across runs; the
suite's `BuildCoordinator` also shares in-progress builds among its workers.

Agent source, bindings, Dockerfile, evaluation profile, SDK requirements and
injected execution code changes can legitimately produce new tags. Editing
shared execution code while a suite is running can therefore produce more
than one image during that suite. Keep those files stable during a run when
comparing cases against the same execution environment.

Historical tags are retained. Docker Desktop's displayed image size includes
shared layers, so summing the sizes of all tags overstates disk consumption.
Do not remove tags automatically: saved results or other containers may still
refer to them.

# StructureClaw

This unit installs the official `@structureclaw/structureclaw@1.1.0` npm package
with a committed npm lockfile. Its registry `gitHead` is
`5224d2dcbc3a74a515938d0d79a36bbaee412492`. The published package contains the
compiled TypeScript LangGraph service, native skills and Python worker assets;
no upstream business code is modified. The repository's current default branch
is not substituted for this published revision.

Run ABB source preparation to materialize `install/` into the ignored `agent/`
directory before building. `npm ci` then installs the pinned package and its
locked dependencies in the container. This is an initially package-based unit,
not a Git import converted into an installation-only unit. The upstream Git
repository's benchmark submodule is not required by the published runtime.

The Docker image uses Linux amd64 because upstream's pinned
`openseespylinux==3.7.1.2` wheel contains an x86-64 ELF shared library despite its
`py3-none-any` filename. ARM hosts require Docker amd64 emulation. Both Node and
Python stages use that architecture. Python analysis dependencies come directly
from the published package's own requirements file.

The outer Python binding forwards the native message/context to a Node process
whose working directory is the installed package root, which the native skill
loader requires. The process invokes `LangGraphAgentService.runFull` and returns
the full graph state, including messages and engineering artifacts. Native
clarification interrupts expose their verbatim questions and options. A following
conversation input in the same binding session uses the native `resumeStream` entrypoint and retains its
chunks plus the public service's full session snapshot. Checkpoints stay in
`/home/agent/.structureclaw`; tool files stay in `/home/agent/workspace`.

ABB's normal LangGraph replacement interception supplies the native OpenAI
compatible credential and replaces the declared request with the run-selected
model. The declared `gpt-4o` request identity is not a provider pin. No actual
provider key is stored in package inputs or settings files. Node inherits ABB's
PEM trust environment; interception and evidence collection remain enabled.

The package's default tool set and disabled shell permission gate are retained.
Local OpenSees analysis is installed. PKPM/YJK commercial Windows applications,
the web frontend and upload HTTP routes are not provided. The native benchmark
entrypoint does not require creating a database-backed web conversation.

Validation and real execution results belong in the run artifacts. The registry
entry remains disabled and adapting until reviewed; configuration or unit-test
success alone does not establish Agent or KUMA acceptance.

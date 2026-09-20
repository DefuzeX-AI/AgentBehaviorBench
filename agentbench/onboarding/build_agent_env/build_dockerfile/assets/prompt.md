# Generate the Agent's outer Dockerfile

Generate ONLY `Dockerfile`, using the supplied source evidence in `context.files`
and the saved `agent.toml` and bindings in `completed_files`. The complete examples
appended below describe different installation strategies. Choose by repository
evidence, not by Agent name. Do not change the saved files or upstream source.

## Build and runtime contract

The build context is the OUTER Agent unit, not its `agent/` source checkout:

The request's build_context is the authoritative directory layout, not a suggested
layout. context.files[].path is relative to agent/; its build_context_path gives
the actual Docker COPY source. A file displayed as requirements.txt therefore
exists at agent/requirements.txt in the build context. A displayed ui/ path is
agent/ui/. Never infer a different root from upstream Dockerfile or README text.
WORKDIR changes the destination base; it never changes COPY source resolution.

```text
unit/                       <- build.context = "."
  Dockerfile                <- the file you generate
  agent.toml
  agent/                    <- original repository
  bindings/                 <- LangGraph only; saved in completed_files
  requirement.md            <- generated separately
  evaluation/               <- optional SDK schemas/fixtures
  .abb-runtime/agentbench/   <- injected by BBA when building
```

- `COPY agent/ ./agent/` under `/opt/agent` produces `/opt/agent/agent/`.
- `COPY .abb-runtime/ /opt/abb-runtime/` plus
  `PYTHONPATH=/opt/abb-runtime` exposes BBA's Python modules; this COPY does NOT
  install either BBA's or the Agent's third-party dependencies.
- Read launch.argv/workdir in the saved manifest. The usual launch is
  `python -m agentbench.runtime.agentcontainer.worker` from `/opt/agent`.
  Do not launch a UI/web server instead or add an ENTRYPOINT that consumes or
  overrides BBA's command. An upstream Dockerfile is evidence, not a file to copy
  blindly: it may be designed for a different server and working directory.
- Copy all saved bindings into `bindings/` beside the image's agent.toml in the
  final runtime stage, normally `COPY bindings/ ./bindings/` under WORKDIR
  `/opt/agent`. Copying into the upstream `agent/` directory is incorrect.
  Use explicit COPY instructions (or COPY --from of a stage containing them),
  rather than hiding this step in RUN commands. Copy any required ancillary
  files only when their existence/content is evidenced. Never invent a lockfile,
  model directory, configuration file or host path to make a COPY look complete.
- Copy the complete source with COPY agent/ ./agent/ so the configured graph JSON,
  entrypoint, transitive imports and assets all exist. Copying only backend/ plus
  application.py can omit langgraph.json and langgraph_entry.py and will not load.
- Follow the selected launch.argv and adapter, not the repository's full product
  deployment. An in-process Python graph does not require building a React/Vue
  frontend merely because the upstream server Dockerfile does. Include frontend
  stages only if the selected invocation actually reads the generated assets.
- Declare a final non-root USER that was actually created. Debian Python slim
  examples use useradd; do not assume that command exists in every base image.

## Select the installation strategy

| Repository evidence | Strategy | Example |
| --- | --- | --- |
| Installable pyproject.toml/setup.py package | Install upstream package and its declared dependencies; include evidenced extras required by the binding. | 01 |
| requirements.txt with loose source, no package build metadata | Install the requirements and expose the source import root. Do NOT force pip install ./agent. | 02 |
| uv.lock with a uv-managed application | Preserve the lock with frozen sync; decide whether the project itself is installable. Use the resulting interpreter at launch. | 03 |
| A supplied pip-compatible hash lock | Install with hashes, then install the project without resolving dependencies again only if that lock covers them. | 04 |
| Local models/tokenizers or platform-specific dependencies | Provision the evidenced assets and compatible dependencies during build. | 05 |

These strategies may combine. A poetry.lock is NOT a pip requirements file.
Do not use `--no-deps` or `--no-build-isolation` without ensuring runtime and build
dependencies are available. Do not invent or hand-select dependency versions to
work around incompatible requirements. Use source installation instructions,
package metadata, Python version files and supplied lock excerpts together.

Choose a Python version satisfying all supplied constraints, including locks and
SDK/runtime requirements. Example versions are not defaults for every Agent.
An excerpt marked truncated is incomplete evidence: missing lines do not establish
absence of a constraint. If a necessary version/extra/system-library requirement
cannot be determined, return needs_input with the specific missing evidence.

## Python environment and imports must agree

The Agent, binding, BBA worker and appended SDK install must use the SAME Python
environment. For a venv, set PATH persistently with ENV; activation inside a RUN
instruction alone does not persist. Ensure that selected Python supports
`python -m pip`, because the SDK overlay uses that exact command. Example 03
explicitly bootstraps pip in its venv.

Install the dependencies imported by the selected binding and worker; OTel alone
does not supply LangGraph or every adapter dependency. Use verified package
constraints supplied by the source/runtime, not made-up versions. The examples
illustrate existing deployments rather than exhaustive requirements for new ones.

For an installed package, prefer normal package imports. For loose source, add
only its verified import root to PYTHONPATH while preserving /opt/abb-runtime.
For `from backend.graph import Graph` with files under `agent/backend/`, that root
is `/opt/agent/agent`. For a src layout it may be `/opt/agent/agent/src`.
Do not assume the binding loader adds arbitrary upstream directories to sys.path.

## Models, writable storage and SDK overlay

If the binding requires local model weights or tokenizers, determine the model ID,
revision and download procedure from supplied evidence. Download at build time
when the deployment requires offline runtime; ensure the final user can read
the assets. Do not copy another Agent's provider, model, retriever or feature flags.
System packages must be justified by actual source/dependency requirements.

The current Docker policy permits root-filesystem writes by the non-root image
user and provides a bounded executable /tmp. Set a real writable HOME and workspace
owned by that user. Do not grant privileged mode or invent host mounts. Native
permissions still apply: a writable filesystem does not make root-owned paths
writable by the Agent.

The SDK overlay appends USER root, installs its own PyPI requirements using
`python -m pip`, copies requirement.md and optional evaluation/, then restores
the final user. Do not duplicate SDK installation or require an empty evaluation/
directory. The overlay may change dependencies, so frozen base installation is
not proof the final evaluation image preserves every locked version.

Never COPY .env, embed credentials, or use broad COPY . when selective COPY is
possible. Keep .abb-runtime available to the build. Quote shell-sensitive pip
constraints (`<`, `>`, `;`). Copy source before installing a local source package.

## Output

Return JSON matching the supplied response schema, not Markdown. Example shape:

```json
{
  "status": "complete",
  "summary": "Explain Python version, installation strategy, interpreter/import paths and required assets.",
  "evidence": ["EXACT_PATH_FROM_CONTEXT_FILES"],
  "missing_information": [],
  "path": "Dockerfile",
  "content": "FULL_DOCKERFILE_TEXT_WITH_NEWLINES"
}
```

Replace explanatory values with real evidence and complete file content. For
needs_input, retain path="Dockerfile", use empty content and concrete questions
in missing_information. Do not claim the image builds or the Agent runs without
actual verification; this request only generates a file.

## ACP containers

When adapter.type is acp, follow framework_requirements.acp and the saved command.
Install the verified CLI and its Node/runtime dependencies; no bindings directory
is required. Keep the Python worker and pip available. Generic BBA worker staging
installs the registered adapter requirements into that interpreter. Create and
chown adapter.cwd and HOME for the final USER. Build-time dependencies and network
access are separate from runtime model/tool endpoint interception.

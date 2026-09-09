# How to Add an Agent to DefuzeX AgentBench

This guide explains how to add a runnable Agent to `defuzeX_AgentBench` and
validate it through the DefuzeX SDK. The current public integration path accepts
LangGraph Agents that can run inside the AgentBench Docker runtime.

Adding an Agent means more than copying source code. A completed integration
must support this full execution path:

```text
resources/registry.toml
        |
        v
AgentRegistry discovers AgentRegistration
        |
        v
CLI prints enabled Agents and requires confirm or cancel
        |
        v
SuiteRunner executes the selected Agents sequentially
        |
        v
RuntimeFactory selects the execution backend
        |
        v
DockerRuntime builds the Agent and starts the Model Interceptor
        |
        v
AgentRunner starts a ContainerAgentAdapter
        |
        v
BenchmarkRunner obtains a DefuzeX SDK Input
        |
        v
Explicit native API caller invokes the Agent
        |
        v
AdapterInvocation(output, raw_output)
        |
        v
SDK Run submits the public output to its Judge
```

## 1. Current Support Boundary

Container startup is independent of Agent communication. Agents keep their native
launch command and API; stdout and stderr are diagnostic streams. See
[Runtime](./Runtime.md) for the lifecycle contract and its current implementation
limits. The in-process LangGraph loader is one adapter, not a requirement for
all containerized Agents. An HTTP service does not need a Graph entrypoint or
an stdin worker to be registered or started.

The legacy SDK evaluation flow needs an explicitly supplied container caller to
translate its inputs into a native API call and its results into harness values.
The Company Research HTTP observation flow is still being implemented.

## 2. Mandatory Admission Requirements

Every requirement below is a hard gate.

| ID | Requirement | Rejection code |
| --- | --- | --- |
| R1 | The native launch method and API are documented. | `MISSING_LAUNCH_DESCRIPTION` |
| R2 | The Agent runs as non-root in the restricted Docker runtime without host networking, privileged mode, a Docker socket, or writable host mounts. | `UNSUPPORTED_EXECUTION_MODE` |
| R3 | The project provides a documented native entry point and callable interface. | `INVALID_ENTRYPOINT` |
| R4 | The Agent is a complete, independently installable project. | `INCOMPLETE_PROJECT` |
| R5 | Inputs map to an explicit Graph state and outputs normalize to JSON-compatible public results. | `UNSUPPORTED_IO_CONTRACT` |
| R6 | Runtime dependencies install in the Agent image without relying on the host Python environment. | `DEPENDENCY_CONFLICT` |
| R7 | The project contains no real keys, `.env`, user data, unsafe install scripts, or malicious behavior. | `SECURITY_REJECTED` |
| R8 | Source URL, fixed revision or snapshot, and a redistributable license are recorded. | `SOURCE_OR_LICENSE_MISSING` |
| R9 | Dockerfile, build context, launch command, environment variables, and model protocol pass review. | `UNSAFE_CONTAINER_BUILD` |
| R10 | Registry discovery, startup, invocation, shutdown, and a minimal SDK benchmark all pass. | `VALIDATION_FAILED` |

Review candidates in this order:

1. Confirm the framework and execution mode.
2. Verify the upstream source, revision, and license.
3. Run the original project outside AgentBench.
4. Identify the Graph entry point and native input/output schema.
5. Review dependencies, environment variables, tools, and side effects.
6. Scan for nested `.git`, `.env`, credentials, caches, and user data.
7. Describe the native API and any optional evaluation input mapping.
8. Build and run the Agent in a clean Docker image.
9. Register the Agent only after the manifest is valid.
10. Run an end-to-end DefuzeX SDK smoke benchmark.

Use this template when rejecting a candidate:

```text
Agent rejected: <agent-id>
Requirement: <R1-R10>
Reason code: <REASON_CODE>
Reason: <specific technical reason>
Evidence: <file, dependency, command, or observed behavior>
Reconsider when: <concrete acceptance condition>
```

## 3. Agent Directory Layout

Place each Agent in a user-named directory, following the
[Agent unit layout](./Layout.md). Numbered names are a convention, not a lookup rule:

```text
resources/agents/<user-defined-name>/
|-- agent.toml             # Required AgentBench manifest
|-- requirement.md         # Requirements and onboarding notes
|-- Dockerfile             # Required isolated build
|-- .dockerignore          # Required restricted build context
`-- agent/                 # Original source, dependencies, README and tests
    |-- langgraph.json     # Upstream graph declarations, for LangGraph projects
    `-- ...                # Preserve the upstream project's internal layout
```

Examples:

```text
01-langgraph-new-project
02-langgraph-chat-agent
03-email-assistant
04-swe-agent
```

The numeric prefix controls display and maintenance order only. It is not part
of the stable Agent ID. For example:

```text
Directory: 03-email-assistant
Agent ID:   email-assistant
```

Directory rules:

- Preserve the upstream license and source information.
- Do not include a nested `.git` directory.
- Do not commit `.venv`, caches, build artifacts, real `.env`, credentials, or
  user data.
- An `.env.example` may contain variable names and placeholders only.
- The project must build without files excluded by `.dockerignore`.

## 4. Create `agent.toml`

Use this Docker Agent template:

```toml
schema_version = "defuzex-bench.agent.v2"
agent_id = "my-langgraph-agent"
display_name = "My LangGraph Agent"
framework = "langgraph"

[source]
url = "https://github.com/example/my-langgraph-agent"
revision = "v1.0.0"
license = "MIT"

[build]
context = "."
dockerfile = "Dockerfile"

[launch]
argv = ["python", "-m", "my_agent"]
workdir = "/opt/agent"

[runtime]
type = "docker"
timeout_sec = 60
env_keys = []
secret_env_keys = []

[llm_interception]
required = true
trust_plugin = "pem-env"

[[llm_interception.credentials]]
id = "primary"
agent_env = "OPENAI_API_KEY"
auth_plugin = "bearer-token"

[[llm_interception.routes]]
id = "openai-chat"
host_patterns = ["api.openai.com"]
ports = [443]
methods = ["POST"]
path_patterns = ["/v1/chat/completions"]
protocol_plugin = "openai-chat"
credential = "primary"

[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
input_key = "prompt"
output_key = "response"
```

### Manifest fields

| Field | Meaning |
| --- | --- |
| `schema_version` | Docker Agents using model interception must use `defuzex-bench.agent.v2`. |
| `agent_id` | Stable globally unique ID; must match the Registry entry. |
| `display_name` | Human-readable name. |
| `framework` | Framework metadata; Docker startup does not require LangGraph. |
| `source.*` | Upstream URL, fixed revision or vendored snapshot, and license. |
| `build.context` | Docker build context relative to the Agent directory. |
| `build.dockerfile` | Dockerfile relative to the build context. |
| `launch.argv` | Original Agent launch command, expressed as an argument list. |
| `launch.workdir` | Container working directory. |
| `runtime.type` | New Agents must use `docker`. |
| `runtime.timeout_sec` | Legacy time budget metadata; a native caller owns request timeouts. |
| `runtime.env_keys` | Allowlisted non-secret host environment variables. |
| `runtime.secret_env_keys` | Required Agent-side secrets; use only after security review. |
| `llm_interception.*` | Transparent traffic patterns, Agent environment, temporary credential bindings, and source protocol plugin IDs. |
| `adapter.*` | Framework entry point and expected Graph I/O metadata. |

`[llm_interception.credentials]` declares only the Agent-facing temporary token.
`agent_env` must name the credential variable the existing model client already
reads. `[llm_interception.environment]` is optional and should contain only
ordinary Agent settings that are actually needed. Do not put model API keys in
`runtime.secret_env_keys`; the run-level `OPENROUTER_API_KEY` is mounted only
into the trusted Interceptor.

For `runtime.type = "docker"`, `[adapter]` records the framework entry point and
expected I/O. The host does not import the Graph. The explicitly supplied API caller performs the
mapping on the host and calls the Agent's native interface. It does not assume
the Agent implements a benchmark-specific worker.

## 5. Register the Agent

Add an entry to `resources/registry.toml`:

```toml
[[agents]]
agent_id = "my-langgraph-agent"
path = "resources/agents/04-my-langgraph-agent"
enabled = true
status = "adapting"
framework = "langgraph"
source = "https://github.com/example/my-langgraph-agent"
case = 5
```

Registry rules:

- `agent_id` must match `agent.toml` exactly.
- `path` is relative to the repository root and must not escape it.
- `enabled = true` makes the Agent available to lifecycle commands.
- Default batch runs select only Agents that are both enabled and `ready`.
- Use `adapting` until `agentbench certify <agent_id>` passes and promotes it
  to `ready`.
- Supported status values are `planned`, `adapting`, `ready`, and `blocked`.
- `framework` must currently be `langgraph`.
- `case` is the number of independent SDK Cases AgentBench requests for this
  Agent. It must be a positive integer and defaults to `1` when omitted.
- The Registry derives the SDK requirement as
  `<registered-agent-path>/requirement.md`; do not add a separate path field or
  Agent-specific lookup branch.

Keep the new entry in `adapting` while completing the implementation and local
tests in the following sections. Do not certify an empty or partially adapted
Agent. Section 13 runs the final certification and owns the transition to
`ready`.

## 6. Declare the LangGraph Entry Point

For LangGraph projects, read `agent/langgraph.json` to inspect the graph declaration.
The manifest's `adapter.config` and graph entrypoint paths are relative to
`agent/`. Keep the upstream graph declaration in that source directory.
It preserves the native LangGraph project contract and identifies the selected
Graph:

```json
{
  "dependencies": ["."],
  "graphs": {
    "agent": "./src/my_agent/graph.py:graph"
  },
  "env": ".env"
}
```

The Graph value must use `relative/file.py:attribute`. The attribute may be:

- A compiled Graph exposing `.invoke()`.
- A zero-argument factory that returns an invokable Graph.

Select one Graph when an upstream repository contains several. Record that
selection in `agent.toml`, the Agent README, and the smoke benchmark. Do not
silently switch to a different Graph because it is easier to run.

## 7. Describe the native API

Document the original command, request endpoints, streaming behavior, input
schema and result retrieval. Keep process startup separate from API invocation.
The Agent may emit arbitrary stdout/stderr logs. There is no mandated worker,
line framing or `ok/output/raw_output` response envelope. The following input
mapping guidance applies only when adapting to the legacy evaluation harness.

### Input mapping

Do not assume all SDK Cases are text. For example, an email Agent may require:

```json
{
  "author": "Alex <alex@example.com>",
  "to": "Lance <lance@langchain.dev>",
  "subject": "API documentation question",
  "email_thread": "Could you confirm the expected timeline?"
}
```

An optional evaluation caller may map this payload to:

```python
{"email_input": payload}
```

DefuzeX SDK may expose immutable mapping objects in the host process. An
evaluation caller should serialize these only when the native API requires it;
the container runtime performs no payload conversion.

### Output normalization

A chatbot may expose a response string. A tool-using Agent should expose stable
business behavior instead of an arbitrary final message:

```json
{
  "classification": "respond",
  "actions": [
    {
      "name": "write_email",
      "arguments": {"content": "I will confirm the timeline by Friday."}
    }
  ]
}
```

The Judge can now evaluate the behavior without depending on internal
LangChain object representations.

## 8. Create the Docker Image

Use a small, non-root image:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/agent
COPY agent/pyproject.toml ./
COPY agent/src ./src
RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 agent

USER agent
```

Do not set an `ENTRYPOINT` when the runtime already supplies `launch.argv`.
Using both creates ambiguous or duplicated commands.

### Runtime filesystem contract

Do not treat the Docker build container and the benchmark runtime container as
the same filesystem. AgentBench runs Agents with a read-only root filesystem and
fresh tmpfs mounts. Files created during `docker build` under runtime tmpfs
paths are hidden when the benchmark starts.

The current Docker runtime provides:

| Path | Runtime behavior | Use |
| --- | --- | --- |
| `/opt/agent` | Image content, read-only at runtime | installed Agent project, config, vendored tools |
| `/tmp` | writable tmpfs with `noexec` | workspaces, state, logs, temporary data |
| `/run/agentbench-tools` | writable executable tmpfs | uploaded tool bundles that must be executable |

Rules:

- Keep source, config files, static fixtures, and bundled tools in the image
  under `/opt/agent` or inside the installed Python package.
- Use `/tmp` only for data that does not need to be executed.
- Use `/run/agentbench-tools` for tool bundles whose `bin/*` files must run.
- Create runtime directories idempotently at process startup, not only in the
  Dockerfile.
- Never weaken the runtime by making all of `/tmp` executable.

For engineering Agents that upload executable tools, point their tool root at
the executable tmpfs:

```dockerfile
ENV SWE_AGENT_TOOLS_ROOT=/run/agentbench-tools
```

For Agents whose config contains relative paths to project files, set an
explicit config root that resolves those paths inside the image:

```dockerfile
ENV SWE_AGENT_CONFIG_ROOT=/opt/agent
```

### Installed package versus source tree

Most Agent images install the project with `pip install .`. After that, Python
imports from `site-packages`, not from the source checkout. Code like this is
usually wrong inside an installed container:

```python
repo_root = Path(__file__).resolve().parents[2]
config_path = repo_root / "config" / "agentbench.yaml"
```

In an installed wheel, that may become a path such as:

```text
/usr/local/lib/python3.11/config/agentbench.yaml
```

Instead, make important runtime paths explicit:

```python
CONFIG_DIR = Path(os.getenv("MY_AGENT_CONFIG_DIR", "/opt/agent/config"))
config_path = CONFIG_DIR / "agentbench.yaml"
```

If the Agent depends on static fixtures, prompts, templates, schemas, or local
test repositories, make sure they are included in the installed package or
copied into the image. For setuptools projects, declare package data explicitly:

```toml
[tool.setuptools]
package-dir = {"" = "src"}
include-package-data = true

[tool.setuptools.packages.find]
where = ["src"]
include = ["my_agent*", "benchmark_mocks*"]

[tool.setuptools.package-data]
benchmark_mocks = [
    "fixtures/example_repo/README.md",
    "fixtures/example_repo/pyproject.toml",
    "fixtures/example_repo/src/example/__init__.py",
    "fixtures/example_repo/tests/test_example.py",
]
```

Add a test that reads `pyproject.toml` and verifies every declared package-data
file exists. This catches the common failure where source checkout tests pass
but the installed Docker image fails with `FileNotFoundError` under
`site-packages`.

### SWE-agent style runtime notes

Some upstream engineering Agents assume they can write to `/root`, install tool
bundles under `/root/tools`, or create repositories directly under `/`. Do not
relax the non-root Docker requirement for those projects. Instead, adapt the
Agent-owned runtime boundary so benchmark writes go to owned paths such as
`/tmp/agentbench-workspaces`, `/tmp/agentbench-home`, and
`/run/agentbench-tools`, and document those environment variables in the
Agent README.

The bundled `04-swe-agent` adapter follows this pattern:

- An optional evaluation caller translates the native API results for the harness.
- `src/swe_agent_benchmark/graph.py` selects the LangGraph wrapper.
- `src/benchmark_mocks/` prepares the deterministic local Python fixture and
  blocks non-LLM network access.
- `SWE_AGENT_CONFIG_ROOT=/opt/agent` makes relative config paths resolve against
  the image project root instead of `site-packages`.
- `SWE_AGENT_TOOLS_ROOT=/run/agentbench-tools` puts executable uploaded tools on
  an executable tmpfs while `/tmp` remains `noexec`.
- `src/sweagent/agent/agents.py` writes autosubmitted patches to
  `SWE_AGENT_MODEL_PATCH`.

Keep `.dockerignore` narrow:

```dockerignore
*
!pyproject.toml
!src/
!src/**
```

The runtime applies additional controls, including a read-only root filesystem,
`cap-drop=ALL`, `no-new-privileges`, PID, memory, and CPU limits. It also mounts
`/tmp` as a fresh writable non-executable tmpfs for each container run and
`/run/agentbench-tools` as a writable executable tmpfs for uploaded tools.
Anything created under these mount points during `docker build` is hidden when
the Agent actually runs. Therefore:

- Do not rely on Dockerfile-created `/tmp/...` directories, caches, sockets,
  state files, or trajectory folders.
- Create `/tmp` subdirectories idempotently at process startup, before the Agent
  imports or asserts paths that live under `/tmp`.
- Keep persistent benchmark artifacts in the host-side AgentBench result files,
  not inside the Agent container.
- If an upstream Agent requires writable runtime paths, expose them through
  documented environment variables and initialize them in the worker or imported
  runtime boundary.
- If an upstream Agent requires executable uploaded tools, point those tools at
  `/run/agentbench-tools`, not `/tmp`.

Docker Agents with model interception share the Interceptor's network namespace.
Matched model requests are intercepted; unmatched traffic is not recorded as
model Trace. Benchmark-specific rules may still prohibit non-model network use.

### Dependency review

Build from a clean image. Do not install Agent dependencies into the AgentBench
host environment.

If the upstream project declares Notebook, evaluation, or deployment packages
that the selected Graph does not use, the Dockerfile may install a reviewed
minimal runtime set and then run `pip install --no-deps .`. Document the reason
and prove the image with an end-to-end run.

For setuptools src layouts, make sure subpackages are included:

```toml
[tool.setuptools.packages.find]
where = ["src"]
include = ["my_agent*"]
```

A declaration such as `packages = ["my_agent"]` may omit
`my_agent.tools` and other required subpackages.

## 9. Configure the Model Interceptor

AgentBench has three separate dependency and trust boundaries:

```text
Host Harness
    `-- DefuzeX SDK creates Cases and Judges submissions

Agent container
    `-- Agent framework and Agent-owned dependencies

Standalone Model Interceptor
    `-- Transparent TLS, provider authentication, streaming, and Trace
```

The DefuzeX SDK is a Host dependency. It must not be installed in the Agent
container or copied into the Model Interceptor image. Likewise, Agent frameworks
such as LangGraph belong to Agent images and are not Interceptor dependencies.

The Agent shares the Interceptor's isolated network namespace. Model traffic
follows this path without changing the Agent's original public URL:

```text
Agent container
    | temporary per-run token
    v
Transparent Model Interceptor
    | OpenRouter target rewrite, TLS Trace, and real credential
    v
OpenRouter
```

The real provider key is mounted only into the Interceptor. The Agent receives
a temporary token in the environment variable expected by its model client.
Matched requests are decoded by the declared source protocol plugin. The
OpenRouter target plugin preserves the protocol skin, maps its endpoint, and
overrides the request model with the run-selected OpenRouter slug. Responses and
SSE chunks are returned using the source protocol skin.

Do not rewrite a compatible Agent to call OpenRouter. Keep its original model
SDK, public provider URL, payload shape, and source model behavior. Declare the
request it already sends in `agent.toml`: the host, port, method, path, source
protocol, credential variable, and authentication plugin. The Interceptor
replaces the request model with the run-selected OpenRouter model before it
leaves the trusted runtime.

Source changes are required only when the original client cannot receive a
temporary credential, cannot trust the runtime CA, pins certificates, uses an
unsupported wire protocol, or does not send normal TCP HTTP model traffic. A
manifest must describe observed behavior; it must not claim capture for traffic
the Interceptor cannot decode and forward.

Required keys are resolved from the process that launches AgentBench:

```powershell
if ($env:OPENROUTER_API_KEY) { "OpenRouter configured" } else { "OpenRouter missing" }
if ($env:OPENROUTER_MODEL) { "OpenRouter model configured" } else { "Use --model" }
if ($env:DEFUZEX_API_KEY) { "DefuzeX configured" } else { "DefuzeX missing" }
```

Never print the values.

`DEFUZEX_API_KEY` is for official DefuzeX Case and Judge Providers.
`OPENROUTER_API_KEY` is for the Model Interceptor. They are independent. Agent
variables such as `OPENAI_API_KEY` contain only temporary per-run tokens.

### Standalone Interceptor deployment

The trusted Interceptor is an independent Python project under
`services/model-interceptor`. Its `pyproject.toml`, source tree, Dockerfile, and
Docker build context are isolated from the root AgentBench package.

In a source checkout, `LocalInterceptorImageProvider` builds that standalone
service. A packaged or production deployment can provide an immutable image:

```powershell
$env:DEFUZEX_MODEL_INTERCEPTOR_IMAGE = "registry.example/model-interceptor:1.2.3"
```

`DockerRuntime` depends only on the `InterceptorImageProvider` contract. Do not add
repository paths, SDK installation rules, or provider-specific image selection
to `DockerRuntime`.

### Adding another model protocol

Model protocols are trusted Interceptor extensions, not Agent dependencies.
Implement the protocol contract and register it through the
`defuzex.model_interceptor.protocols` Python entry-point group. A protocol
decodes request/response JSON and SSE for Trace.

Authentication plugins validate temporary credentials and inject the trusted
upstream credential through `defuzex.model_interceptor.auth`. Target provider
plugins rewrite the upstream endpoint and model through
`defuzex.model_interceptor.targets`. OpenRouter is the built-in target.

CA behavior uses `defuzex.model_interceptor.trust`. Only reviewed plugins may be
installed in trusted images; an Agent manifest cannot install arbitrary plugins.

## 10. Conversation State

For Graphs with a LangGraph checkpointer, `BenchmarkRunner` passes:

```python
{"configurable": {"thread_id": sdk_run.run_id}}
```

Inputs in one SDK Run therefore share state. Different SDK Runs use different
thread IDs. A custom worker must pass the received `run_config` to the Graph.

Test both properties for stateful Agents:

- Two inputs in one Run share the expected conversation history.
- Separate Runs do not share state.

## 11. Create the SDK Requirement File

Every Agent that uses the official DefuzeX Case Provider needs an explicit
requirement file. Store the repository defaults under:

```text
resources/agents/<user-defined-name>/requirement.md
```

The requirement is a UTF-8 Markdown file with YAML front matter and three
required, non-empty level-two sections:

```markdown
---
agent_description: "A concise description of the Agent under test."
input_type: text
---

## Production Use Scenario

Describe where and why the Agent is used.

## Behaviors to Test

Describe observable behavior that generated Cases should exercise.

## Known Limitations or Prohibited Behaviors

Describe unsupported capabilities, forbidden side effects, and safety limits.
```

### Front matter rules

The SDK accepts only these front matter fields:

| Field | Required | Meaning |
| --- | --- | --- |
| `agent_description` | Yes | Non-empty Agent summary sent to the official Case service. |
| `input_type` | Yes | `text` or `structured`. |
| `input_schema` | Structured only | Relative path to a local JSON Schema file. |

Unknown front matter fields are rejected. The file must start with `---`, close
the front matter with another `---`, and contain all three exact English
headings shown above. The SDK also recognizes its documented Chinese heading
aliases, but AgentBench requirement files should use English.

The official Case Provider currently generates `text` Inputs only. Therefore,
all requirement files intended for official Case generation must declare:

```yaml
input_type: text
```

If an Agent natively expects an object, its Worker must define a safe and
documented text-to-state mapping. The email Agent, for example, wraps official
text as a synthetic incoming email before invoking its Graph.

`structured` requirements are available only to custom Case Providers. They
must declare either `input_schema` in front matter or an `## Input Schema`
section containing a JSON code block. Schema `$ref` values may be internal only;
the SDK never retrieves external schemas.

### Content and privacy limits

For official Case generation:

- `agent_description` is limited to 2,000 characters.
- Each required behavior section is limited to 4,000 characters and 8 KiB.
- The combined structured behavior specification is limited to 16 KiB.
- Do not include credentials, tokens, private user data, or hidden rubrics.
- Describe observable behavior, not implementation-specific chain of thought.

The official Provider sends the validated Agent description, the three behavior
sections, and restricted repository metadata. It does not need a private rubric
inside the local requirement file.

### Validate requirements locally

Validate all repository requirements before contacting the official service:

```powershell
python -B -c `
  "from pathlib import Path; from defuzex.requirements import parse_requirement; [parse_requirement(path) for path in Path('resources/agents').glob('*/requirement.md')]; print('Requirements valid')"
```

Parsing is offline and fails on malformed front matter, missing sections,
unsupported input types, missing schemas, invalid JSON Schema, and unsafe
external `$ref` values.

### Requirement lookup

`AgentRegistry` derives the requirement path from the registered outer directory:

```python
registration.requirement_path
# <repo>/resources/agents/<user-defined-name>/requirement.md
```

Normal official runs do not pass a path manually:

```python
result = BenchmarkRunner().run_defuzex(
    registration,
    track_files=False,
)
```

`BenchmarkRunner` automatically forwards `registration.requirement_path` to the
SDK. An explicit `requirement_path=` remains available only as an override for
temporary experiments and tests.

Use one requirement per Agent. Chat, deterministic starter, and email behavior
have different contracts and must not share a generic requirement.

## 12. Add Tests

### Registry test

```python
def test_find_my_agent() -> None:
    registry = load_registry(REPO_ROOT / "resources" / "registry.toml")
    agent = registry.find("my-langgraph-agent")

    assert agent.framework == "langgraph"
    assert agent.status == "adapting"
    assert agent.path.name == "04-my-langgraph-agent"
    assert agent.path.joinpath("agent.toml").is_file()
```

CLI tests must derive the default run count from `registry.ready()`. Do not
hard-code the number of Agents, because every certified registration would
require an unrelated test edit.

### Runtime configuration test

Parse the manifest without starting Docker and assert:

- `launch.argv`
- invocation timeout
- native model host, path, protocol, and credential environment variable
- optional Agent environment overrides, when present
- RuntimeFactory selects `ContainerAgentAdapter`

### Worker and transport test

Cover:

- string and structured inputs
- immutable mappings from the SDK
- invalid or missing fields
- JSON-compatible public output
- stdout/stderr diagnostics and native API responses
- safe errors

### Docker integration test

Use a deterministic local model endpoint for normal CI smoke coverage. The run
must still traverse DockerRuntime, Model Interceptor, LangGraph, and DefuzeX SDK.
Keep real provider calls as explicitly selected integration tests.

After installing pytest, run:

```powershell
cd <path-to>\defuzeX_AgentBench
python -m pytest -q
```

## 13. Certify the Adapted Agent

Certification is the final onboarding gate after local, transport, and Docker
tests pass. Keep the Registry entry enabled and in `adapting` before running it:

```toml
enabled = true
status = "adapting"
```

Run only the newly adapted Agent through the complete DefuzeX flow:

```powershell
cd <path-to>\defuzeX_AgentBench
python -m agentbench certify my-langgraph-agent
```

The command always creates a unique atomically updated certification artifact under
`results/`, even without `--output`. It executes Registry and requirement
validation, Agent startup, DefuzeX Case generation, every SDK Input, and the
DefuzeX Judge.

Certification checks whether the adapter is runnable and whether every
requested Case completes without invocation/runtime errors. It is not a score
threshold. A Judge failure means the Agent performed poorly on the benchmark,
but it can still be certified as `ready` if the container, worker, model
Interceptor, input mapping, output serialization, and cleanup all completed.

### Certification promotes to ready

When the Agent completes all requested Cases without invocation errors,
AgentBench atomically changes only the target Registry entry:

```toml
status = "ready"
```

If the benchmark also passes, the command ends with output similar to:

```text
Suite complete: 1 passed, 0 failed, 0 skipped, 1 selected.
Certification passed. Agent 'my-langgraph-agent' is now ready.
```

If the Agent completes all Cases but the Judge marks the behavior as failing,
the command still promotes the adapter and reports the benchmark failure:

```text
Suite complete: 0 passed, 1 failed, 0 skipped, 1 selected.
Certification completed with benchmark failures. Agent 'my-langgraph-agent' is now ready.
```

At this point onboarding has succeeded. The Agent is eligible for the next
default `agentbench run`, and the certification JSON is the review evidence.
Do not make a second manual status edit. Benchmark quality should be improved
with separate Agent, prompt, model, or requirement work.

### Certification remains adapting

A certification remains in `adapting` only when the execution boundary did not
complete: configuration failed, the Agent failed to start, the native API caller
returned an invocation error, one or more requested Cases did not complete, or
the Registry update failed. This is intentional: execution evidence must be
investigated before the Agent can enter default batch runs. Do not bypass the
gate by manually changing the status to `ready`.

Use the exact artifact path printed by the failed command:

```powershell
python -m agentbench view `
  results\certify-my-langgraph-agent-<timestamp>.json
```

Classify the first failing boundary before changing code:

| Failing stage | Inspect first |
| --- | --- |
| SDK configuration check | `DEFUZEX_API_KEY`, requirement parsing, Provider selection, and required packages. |
| Starting Agent | `agent.toml`, Docker build, non-root permissions, read-only filesystem, `/tmp` initialization, and worker command. |
| Generating Case | requirement content, official service response, API configuration, and sensitive-data rejection. |
| Running Agent inputs | Native API responses, process logs, Interceptor variables and Trace, timeout, and output serialization. |
| DefuzeX Judge or `Judge: issue` with completed Cases | public normalized output, requirement criteria, missing evidence, and benchmark quality. This should not block `ready`. |
| Registry update after completed execution | target `status` field and whether another process edited the Registry during certification. |

Then follow this loop:

1. Decide whether the failure is fixable inside the adapter, worker, manifest,
   Docker image, requirement, or interception route.
2. Apply the smallest relevant fix and add a regression test for the observed
   failure.
3. Re-run the focused tests and Docker smoke test.
4. Run `python -m agentbench certify my-langgraph-agent` again.
5. Repeat until certification completes all Cases and performs the `ready`
   transition.

If the upstream Agent fundamentally violates the current admission boundary and
cannot be repaired without weakening security or benchmark contracts, document
the incompatibility and change it to `blocked`; do not present an unverified
Agent as ready.

See [`CLI.md`](./CLI.md) for complete command arguments, artifact naming,
viewer behavior, and exit codes.

## 14. Run Through the DefuzeX SDK

### Batch suite entry point

The installed `agentbench` command is the normal batch entry point:

```powershell
agentbench
```

`agentbench` remains a compatibility alias for `agentbench run`. The CLI is
organized as registered command features under `agentbench/cli/features/`, so
each command owns its parser and workflow without adding dispatch branches to
the root entry point.

The run command performs the following steps:

1. Load enabled, `ready` registrations from `resources/registry.toml`.
2. Report enabled `adapting` Agents as excluded from the batch.
3. Print the selected Agents and require `yes` or `no` (`y` and `n` work).
4. Pass the confirmed registrations to `SuiteRunner`.
5. Run one `BenchmarkRunner` execution per Agent in Registry order.
6. Print each result and a final passed, failed, skipped, and selected summary.
7. Return exit code `0` only when every selected benchmark passes.

Lifecycle commands are:

```powershell
agentbench run --output results\result.json
agentbench view results\result-20260819-025720.json
agentbench certify my-langgraph-agent
```

`certify` is intentionally host-controlled. The Agent container does not
promote itself. A ready Agent is treated idempotently, while `planned` or
`blocked` Agents must first be moved to `adapting` by a maintainer.

Progress output reflects real Harness boundaries:

```text
Checking DefuzeX SDK configuration...
  OK | Provider mode: official

------------------------------------------------------------------------------
Running: [1/3] langgraph-new-project
Starting Agent...
  OK | LangGraphAdapter
Generating Case from DefuzeX Server...
  OK | run=<sdk-run-id>
Running Agent inputs and DefuzeX Judge...
  OK | Judge: pass
```

`OK` is green and `FAILED` is red in an ANSI-capable terminal. SDK preflight
checks package availability, Provider selection, requirement resolution, and
official Key format without contacting the Server. Agent startup happens
before remote Case generation. Therefore, a long pause after the Case message
means the SDK is waiting on the official Server, while a long pause after the
Agent message means the runtime is loading or building the Agent.

CLI animation timing, separator width, and ANSI colors are centralized in
`agentbench/cli/constants.py`. Keep presentation delays in the CLI; Harness and
Runner code must never sleep for visual effects.

`SuiteRunner` continues after an individual Agent startup, invocation, or Judge
failure by default, so one broken Agent does not hide the remaining results.
Set `continue_on_error=False` for fail-fast execution. Shared Provider
configuration errors are always raised immediately because retrying the same
invalid configuration for every Agent cannot succeed.

The CLI uses the trusted host process for DefuzeX SDK orchestration and passes
`allow_local=True` to that SDK Run. This does not run untrusted Agent code on
the host: model-backed Agents still execute through AgentBench DockerRuntime,
and the OpenRouter credential remains in the Model Interceptor.

Programmatic batch execution uses the same Runner:

```python
registry = load_registry("resources/registry.toml")
result = SuiteRunner().run_defuzex(
    registry.ready(),
    allow_local=True,
    track_files=False,
)

if not result.passed:
    raise RuntimeError("At least one Agent benchmark failed")
```

Do not implement Agent iteration in the CLI or inside `BenchmarkRunner`.
`SuiteRunner` owns suite ordering and aggregation, `BenchmarkRunner` owns one
SDK handshake, and `AgentRunner` owns one Agent lifecycle.

### Local Provider mode

Pass a Case Provider and Judge Provider together:

```python
result = BenchmarkRunner().run_defuzex(
    registration,
    case_provider=my_case_provider,
    judge_provider=my_judge_provider,
    max_inputs=1,
    allow_local=True,
    track_files=False,
)
```

Requirements:

- Both Providers must be supplied.
- The Case Provider returns `inputs` and a public `rubric`.
- `max_inputs` must be positive.
- The Judge evaluates the normalized public output, not framework internals.

### Official Provider mode

Do not pass custom Providers:

```python
result = BenchmarkRunner().run_defuzex(
    registration,
    track_files=False,
)
```

Requirements:

- `DEFUZEX_API_KEY` is available, or `api_key=` is passed explicitly.
- `<registered-agent-path>/requirement.md` exists and is valid.
- The SDK selects the official Case and Judge Providers.

If neither an official key nor a complete local Provider pair is configured,
BenchmarkRunner stops before starting the Agent.

## 15. Troubleshooting

### Registry detects the Agent, but startup fails

Registry discovery proves only that the directory and basic manifest are valid.
Check:

- Docker is available.
- The image installs the Agent and all Python subpackages.
- `launch.argv` imports successfully in a clean container.
- Required environment variables exist in the launching process.
- The Docker build context contains every required file.

### `mappingproxy is not JSON serializable`

The SDK may freeze structured Case payloads. Docker transport must accept
generic Mapping values and convert them to JSON objects. Do not restrict the
transport to built-in `dict` instances.

### `ModuleNotFoundError` for an Agent subpackage

Inspect setuptools package discovery. A top-level package declaration may omit
nested packages. Prefer `[tool.setuptools.packages.find]` and verify the result
in a clean image.

### `FileNotFoundError` under `site-packages`

Example:

```text
FileNotFoundError: /usr/local/lib/python3.11/config/agentbench.yaml
```

The Agent is probably deriving project root from `Path(__file__)` after
`pip install .`. In Docker, imported code lives under `site-packages`, not the
source checkout. Fix the adapter by reading config, prompts, schemas, and tool
paths from explicit environment variables such as `MY_AGENT_CONFIG_DIR` or
`SWE_AGENT_CONFIG_ROOT`.

### Static fixture missing in the installed image

Example:

```text
FileNotFoundError: .../site-packages/benchmark_mocks/fixtures/buggy_repo_template
```

The fixture exists in the source tree but was not included in the installed
wheel. Add setuptools package-data entries or copy the fixture into the image
under `/opt/agent`, then add a test that verifies every declared fixture file is
present before Docker build.

### Tool exists but `which <tool>` fails or returns permission denied

Example:

```text
RuntimeError: Tool str_replace_editor is not available in the container.
```

Check the runtime mount:

```bash
mount | grep agentbench-tools
```

Executable tools must not be uploaded under `/tmp`, because `/tmp` is mounted
with `noexec`. Use `/run/agentbench-tools` for uploaded tool bundles and ensure
the runtime policy mounts it with `exec`. The file can show `755` and still fail
with `Permission denied` when the mount itself is `noexec`.

### The Agent works locally but not in AgentBench

Local editable installs, `.env`, Notebook paths, and globally installed packages
can hide missing dependencies. Reproduce the manifest command in a clean image.
Do not fix container failures by installing the Agent into the Harness Python
environment.

### The Graph requires `thread_id`

Pass the received `run_config` through the worker. BenchmarkRunner already uses
the SDK `run_id` as the LangGraph `thread_id`.

### Output cannot be judged

Normalize the output around observable business behavior. Put stable strings,
classifications, tool names, and safe arguments in `output`. Do not submit raw
LangChain objects or credentials.

### Containers or networks remain after a failed run

Treat this as a Runtime cleanup defect. `close()` and exception paths must remove
the Agent container, Interceptor container, temporary networks, and secret files.

## 16. Email Assistant Integration Lessons

`03-email-assistant` was the first Docker Agent with structured input and
tool-oriented output. Its integration exposed several reusable issues:

| Problem | Observed failure | Fix |
| --- | --- | --- |
| SDK froze the structured payload | `mappingproxy` failed JSON serialization | DockerSession now accepts generic mappings. |
| Upstream package metadata included only the top package | Container could not import `email_assistant.tools` | Setuptools now discovers `email_assistant*`. |
| The Graph had no final chat response | A string-only Judge could not evaluate behavior | Worker returns `classification` and normalized `actions`. |
| Dockerfile and manifest both defined startup | Container command ownership was ambiguous | Runtime uses `launch.argv` only. |

The smoke Case asks for a direct email response. The successful path observes:

```text
classification: respond
actions: write_email, Done
judge: pass
```

During onboarding, run this Case through `agentbench certify email-assistant` so
the same Docker, Interceptor, SDK, and Judge path used by normal benchmarks is
exercised.

## 17. Definition of Done

The integration is complete only when every item is verified:

- [ ] R1-R10 pass.
- [ ] Agent is under `resources/agents/<order>-<agent-id>`.
- [ ] Stable Agent ID matches `agent.toml` and Registry.
- [ ] Numeric directory prefix is not part of the Agent ID.
- [ ] No nested `.git`, `.venv`, real `.env`, credential, cache, or user data is committed.
- [ ] Source URL, fixed revision or snapshot, and license are recorded.
- [ ] `<registered-agent-path>/requirement.md` passes the selected SDK's parser.
- [ ] README documents setup, selected Graph, input, output, keys, and run command.
- [ ] Dockerfile builds from a restricted context and runs as non-root.
- [ ] Runtime paths are explicit; code does not infer project root from
      `site-packages`.
- [ ] Static fixtures, prompts, schemas, and templates used at runtime are
      included in the image or package data.
- [ ] Executable uploaded tools use `/run/agentbench-tools`; non-executable
      temporary data uses `/tmp`.
- [ ] Native API calls and result retrieval are validated.
- [ ] Model-backed Agents declare their native traffic accurately; the trusted
      Interceptor captures it and the real model key stays outside the Agent
      container.
- [ ] RuntimeFactory selects the expected execution backend.
- [ ] AgentRunner starts, invokes, and stops the Agent.
- [ ] Stateful Agents have thread isolation tests.
- [ ] Local or official DefuzeX SDK benchmark completes without invocation or
      runtime errors.
- [ ] Registry, CLI, runtime, transport, and Runner tests pass.
- [ ] Failure cleanup leaves no Agent containers, Interceptor containers,
      networks, or secret files.
- [ ] Logs and exceptions do not expose credentials.
- [ ] `agentbench certify <agent_id>` exits with `0` and saves its JSON
      evidence.
- [ ] Certification changed the target Registry status to `ready`; any Judge
      failures are tracked as benchmark-quality work, not adapter-readiness
      blockers.

Only a certification that completed all requested Cases without invocation or
runtime errors should set `status = "ready"`. Keep execution-failing
adaptations in `adapting` while they are being repaired, or mark a documented,
fundamentally incompatible integration as `blocked`.

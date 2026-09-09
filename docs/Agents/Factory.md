# AgentFactory Flow

AgentFactory is the staging flow for turning a downloaded LangGraph Agent into a
repeatable AgentBench candidate. Do this before copying anything into
`resources/agents/`.

## Queues

Before converting an Agent, create an AgentFactory workspace. This workspace
keeps downloaded Agent copies, active conversions, review candidates, and
Docker-accepted Agents separate from the AgentBench repository.

Create the workspace from your benchmark workspace:

```powershell
mkdir AgentFactory
mkdir AgentFactory\PrepareAgents
mkdir AgentFactory\ProcessAgents
mkdir AgentFactory\InreviewAgents
mkdir AgentFactory\DoneAgents
```

The resulting structure should look like:

```text
AgentFactory/
  PrepareAgents/
  ProcessAgents/
  InreviewAgents/
  DoneAgents/
```

Use one Agent directory in exactly one queue:

| Queue | Meaning |
| --- | --- |
| `AgentFactory/PrepareAgents/<agent-name>/` | Downloaded source, not yet analyzed. |
| `AgentFactory/ProcessAgents/<agent-name>/` | Active conversion work. |
| `AgentFactory/InreviewAgents/<agent-name>/` | Code conversion done, awaiting review or Docker E2E. |
| `AgentFactory/DoneAgents/<agent-name>/` | Docker E2E passed; ready to copy into AgentBench. |

Do not move a partial Agent directly into `resources/agents/`.

## Five Stages

1. Analyze the Agent.
   Find the graph, state schema, model creation code, network calls, startup
   command, existing Docker files, and the representative task.
2. Describe the native LLM traffic.
   Keep the existing SDK, provider URL, request shape, and source model behavior.
   Record the real host, port, method, path, protocol, and credential environment
   variable for `agent.toml`. Change model code only when transparent capture is
   incompatible with the client.
3. Build business mocks.
   Put deterministic non-LLM services in `benchmark_mocks/`. Do not let missing
   mock coverage fall back to real network.
4. Stabilize runtime.
   Add `langgraph.json`, Dockerfile, `.env.example`, package metadata, and a
   non-interactive smoke path.
5. Accept in Docker.
   Build the image, run the representative task through the Model Interceptor,
   verify the captured request/response and mock traces, then verify missing host
   credentials fail clearly.

Only after stage 5 should the Agent move to `DoneAgents/`.

## Conversion Rules

- Preserve the Agent's real workflow; do not turn it into a simple chat wrapper.
- Prefer a wrapper and manifest declaration over edits to the Agent's model
  construction. AgentBench, not Agent source, selects the OpenRouter target
  model and holds the real provider credential.
- LLM is the only allowed real network dependency.
- All search, SaaS, database, finance, email, browser, or repository services
  must be mocked locally unless they are the model provider.
- Mock traces should record service name, operation, and a safe summary.
- No `.env`, API keys, tokens, user data, caches, or nested `.git` directories.
- The Agent may receive a temporary model token in the environment variable its
  existing client already expects. Never put the real OpenRouter key in the
  Agent image or manifest.
- Final report must include build command, run command, exit codes, task output,
  mock trace summary, missing-key behavior, and remaining limitations.

## Handoff To AgentBench

When an Agent reaches `DoneAgents/`, copy a minimal reviewed version into:

```text
resources/agents/<user-defined-name>/
  agent/           # upstream source
  requirement.md
  Dockerfile       # ABB build, context = outer directory
  agent.toml       # ABB runtime and launch declaration
```

The [Agent unit layout](./Layout.md) defines how these paths are read. Keep
source configuration and dependency files inside `agent/`; keep ABB adaptation
files outside it.

Then register it as:

```toml
enabled = true
status = "adapting"
```

Certification owns the transition to `ready`.

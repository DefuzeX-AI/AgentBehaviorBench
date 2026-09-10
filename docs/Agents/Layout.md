# Agent unit layout

Each registered Agent has a user-named directory. The registry `path` selects
that directory; its name does not have to match `agent_id` or the upstream repo.

```text
resources/agents/01-company-research-agent/
├── agent/              # original source checkout, including its dependency files
├── requirement.md      # behavior requirements and onboarding notes
├── Dockerfile          # ABB image build instructions
├── .dockerignore       # exclude Git metadata, secrets and caches from the image
└── agent.toml          # ABB identity, source provenance, runtime and adapter settings
```

`requirement.md` is Markdown, not a pip dependency file. The registry checks
that it exists. An evaluation SDK may impose its own content schema later.
Python dependencies such as `requirements.txt` stay inside `agent/`.

## Reading paths

| Reader | Base directory | What it reads |
| --- | --- | --- |
| Registry | repository root | the explicitly registered `path` |
| Registry | outer Agent unit | `agent.toml`, `requirement.md`; checks `agent/` and `Dockerfile` exist |
| Runtime factory | outer Agent unit | `agent.toml` → `runtime.type` |
| Docker runtime | outer Agent unit | `[build]`, `[launch]`, `[runtime]`, `[llm_interception]` |
| LangGraph adapter | outer Agent unit | `[adapter]` in `agent.toml` |
| LangGraph configuration | `agent/` | `adapter.config`, e.g. `langgraph.json` |
| LangGraph loader | `agent/` | graph `file.py:attribute`; imports from `agent/` or `agent/src/` |

There is no fallback to `resources/requirements/<agent_id>.md` or to graph
source beside the outer manifest. Migrate flat projects by moving their source
to `agent/`, keeping ABB metadata outside, and relocating the requirement.

Use the outer directory as the Docker build context:

```toml
[runtime]
type = "docker"

[build]
context = "."
dockerfile = "Dockerfile"
```

Docker `COPY` paths consequently begin with `agent/`. The upstream Dockerfile
may remain at `agent/Dockerfile`; ABB uses the outer one. Container paths such
as `/opt/agent` are defined by that Dockerfile and `launch.workdir`, independently
of host paths. The runtime still requires a complete `[launch]` declaration.

```text
CLI or Python caller → load_registry → user-named outer directory
  → requirement.md
  → agent.toml → runtime.type
      → docker: outer Dockerfile + agent/ → image → launch.argv
      → in_process: agent/langgraph.json → agent/<entrypoint> → graph
```

These readers belong to the library. No new CLI-only lookup is involved.
The framework loader does not automatically run inside the Docker branch;
that branch executes the configured container command.

## Current Company Research status

See the unit's `requirement.md` and retained certification results for current
readiness evidence. Docker execution and evaluation have been observed, but no
complete certification transition record was retained in this checkout at the
2026-09-10 audit, so the registry is `adapting` pending certification. Judge
quality issues alone never determine readiness.

Dockerfile and build/launch configuration are required only for `runtime.type =
"docker"`; in-process units need no placeholder Dockerfile. Build file paths are
resolved relative to `build.context`, with the same validation at registration
and execution, without loading credentials during registration.

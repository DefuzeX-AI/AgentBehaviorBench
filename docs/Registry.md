# Understanding `registry.toml`

English | [中文](otherLanguages/Registry.zh-CN.md) | [Français](otherLanguages/Registry.fr.md) | [日本語](otherLanguages/Registry.ja.md) | [한국어](otherLanguages/Registry.ko.md)

[Back to README](../README.md) · [How to start ABB](Guide.md)

The [Agent registry](../resources/registry.toml) records the target Agents available
to ABB, their local integration directories, and their default evaluation budgets.
`agentbench run` selects entries with both `enabled = true` and `status = "ready"`.

## Read an entry

The file starts with a schema version. Each `[[agents]]` block adds one Agent:

```toml
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "folder-mover-agent"
path = "resources/agents/01-folder-mover-agent"
enabled = false
status = "ready"
framework = "langgraph"
source = "C:\\Song_startup\\benchmark\\04-folder-mover-agent\\folder-mover-agent"
case = 1
step = 3
```

This example describes a registered LangGraph Agent with a default budget of one
independent Case and at most three dialogue steps per Case. It is marked `ready`,
but disabled, so `run` excludes it. The source path is an example of the original
import location on one machine; it is not a path that every user needs to create.

| Field | Meaning |
| --- | --- |
| `schema_version` | File-level format identifier. Keep `"defuzex-bench.registry.v1"`; write it once, before the Agent blocks. |
| `[[agents]]` | TOML array-of-tables syntax: each block is a separate Agent registration. |
| `agent_id` | Unique Agent identifier used in CLI commands. Must match `agent_id` in that Agent's `agent.toml`. |
| `path` | Local integration directory, resolved relative to the repository root for the standard registry location. Points to the outer directory containing `agent.toml` and `requirement.md`, not its inner `agent/` source directory. It must remain inside the repository. |
| `enabled` | Whether the Agent is available for selection. `false` excludes it from `run` and from single-Agent `evaluate` selection. Use a TOML boolean; defaults to `true` if omitted. |
| `status` | Integration lifecycle label. `adapting` means integration is awaiting certification; `ready` permits default `run` selection when enabled. Defaults to `unknown` if omitted, which `run` excludes. |
| `framework` | Framework label, such as `langgraph` or `acp`. Keep it consistent with the Agent's manifest and actual integration. The runtime adapter and launch configuration are defined in `agent.toml`. |
| `source` | Original source location, such as a repository URL or local import directory. It documents origin; changing it does not replace the imported code or configure startup. Defaults to an empty string. |
| `case` | Number of independent Cases to evaluate for this Agent. Must be a positive integer; defaults to `1`. |
| `step` | SDK upper bound on dialogue steps per Case. Must be a positive integer when present; if omitted, the SDK supplies its default. Actual Cases may contain fewer steps. |

`agent_id`, `path`, and `framework` are required, nonempty strings. In a TOML
double-quoted string, escape Windows backslashes as `\\`, as shown above.

## Understand `case` and `step`

- `case = 1`, `step = 3`: one independent Case, with up to three ordered inputs.
- `case = 5`, `step = 3`: five independent Cases, each with up to three ordered inputs.
- A dialogue step submits an input to the target Agent. Its execution can contain
  several model calls and tool calls, so `step` is not a tool-call limit or an Agent's
  internal reasoning-iteration limit. `case` and `step` also do not set concurrency.

Some Agents do not support multiple dialogue steps, so we recommend keeping the
default `step` value configured by the benchmark for each Agent.

The selected SDK applies the step budget during Case generation and execution.
Explicit SDK `max_steps` options override the registry's `step`. For `evaluate`,
`--cases` overrides `case` and `--max-steps` overrides the step budget for that run,
without editing the registry:

```bash
agentbench evaluate react-agent --cases 2 --max-steps 3 --no-view
```

## Select Agents and change defaults

To include the example Agent in `run`, set its `enabled` field to `true`. For a new
integration marked `adapting`, complete [Agent onboarding](How%20To%20Add%20Agent.md)
and certify it while enabled:

```bash
agentbench certify folder-mover-agent --no-view
```

Certification promotes a successfully integrated Agent to `ready`. The label
records integration readiness; it does not guarantee that Judge will find no
behavioral defects. Manually changing the label does not perform certification.
Unlike `run`, `evaluate` selects an enabled Agent without filtering on `ready`.

```bash
agentbench observe --list
agentbench run --no-view
```

Edit `case` and `step` to change future runs' default budgets. Saved Cases and
results keep their recorded configuration. `run` loads and validates every registry
entry before selecting enabled, ready Agents, so a disabled entry with missing
integration files can still prevent the registry from loading. Keep paths valid,
identifiers unique, and required integration files in place. For an overview of
the registered sources, see [Included Agents](Agents.md).

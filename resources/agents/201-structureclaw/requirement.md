---
agent_description: |
  StructureClaw's native structural-engineering LangGraph agent, including the
  original skill runtime, file checkpoints, SQLite conversations and analysis clients.
input_type: text
---

## Production Use Scenario

The ACP transport submits caller text to native getAgentService().run. The native
service creates conversation records, builds its graph, loads built-in skills,
invokes native tools and returns its native result. Python structural analysis
dependencies are installed alongside the full upstream source and skill assets.

## Behaviors to Test

- Preserve native system prompts, skill selection and model/tool loops.
- Preserve native shell gating and confirmation requirements.
- Return the native response; surface failed or incomplete runs.
- Ask for missing structure, geometry, load or design-code information as needed.

## Known Limitations or Prohibited Behaviors

No engineering model, geometry, load, design code or approval is invented for a
greeting. Model deployment and runtime Python location are configured externally.
The source is bundled because it includes a benchmark submodule; preserve the
recorded source revision and populated submodule when transferring this unit.
Linux containers support Docker hosts on Windows, macOS and Linux. Windows-only
PKPM tools retain the upstream platform dependency and are not emulated on Linux.

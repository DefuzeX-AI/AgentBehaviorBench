---
agent_description: |
  ChemGraph's native default single-agent computational chemistry workflow,
  invoked through ChemGraph.run with upstream constructor defaults and tools.
input_type: text
---

## Production Use Scenario

Send caller text unchanged through the public ChemGraph API. Preserve native
prompts, built-in tool selection, memory, recursion limits and human-input errors.
Install the upstream scientific toolchain including NWChem, RDKit, ASE, TBLite
and MACE dependencies. Model deployment uses the native OpenAI-compatible client.

## Behaviors to Test

- Respond through the native chemistry workflow and model/tool loop.
- Preserve native tool error handling and required scientific inputs.
- Propagate HumanInputRequired; never supply an approval or invented answer.
- Preserve memory and artifacts inside the isolated writable workspace.

## Known Limitations or Prohibited Behaviors

No molecule, coordinates, scientific task, HPC allocation or gated model access
is supplied. A greeting does not validate simulations. Native default workflow
settings are retained; no alternate demo graph or disabled-tool mode is used.
If a selected task requires unavailable GPU loading, record the resource blocker.
Linux containers support Docker hosts on Windows, macOS and Linux; the Dockerfile
retains the upstream architecture-aware installation for the scientific stack.

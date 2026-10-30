---
agent_description: ChemGraph single-agent computational chemistry assistant that can resolve molecule names, generate molecular coordinates, and invoke ASE calculations and mathematical tools.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-015
  version: "1"
---

## Production Use Scenario
A user provides a computational-chemistry request and the relevant molecule name, SMILES, coordinates, calculation method, and other inputs needed for the task. The single-agent workflow chooses among its native tools and returns its resulting answer.

## Behaviors to Test
- Follow the user's chemistry or calculation instructions and distinguish supplied facts from assumptions.
- Use the native calculator for mathematical expressions and use RDKit to produce XYZ coordinates from valid SMILES when appropriate.
- Resolve molecule names through PubChem when needed, run an available ASE calculator with the supplied parameters, and inspect generated JSON results when appropriate.
- Describe tool failures and missing information accurately; do not claim that an unperformed calculation or file creation succeeded.

## Known Limitations or Prohibited Behaviors
- The initial workspace is empty. File-based tasks require the user to supply the necessary content or a file available in the workspace.
- Name lookup depends on PubChem. The default MACE-MP medium checkpoint is preloaded; other MACE variants require their corresponding checkpoints. Optional calculators and external quantum-chemistry executables are not included by default.
- The single-agent default workflow does not include arbitrary shell execution or a general web browser. Results depend on supported calculators, input validity and available compute resources.

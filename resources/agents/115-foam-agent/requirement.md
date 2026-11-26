---
agent_description: |
  The native Foam-Agent LangGraph workflow for OpenFOAM case preparation,
  meshing, solver planning, input generation, reviews, execution and visualization.
input_type: text
---

## Production Use Scenario

The supplied text enters the upstream `main` workflow unchanged. The integration
uses the upstream OpenFOAM image build, hydrated tutorial corpus and pinned
Qwen embedding assets. Only the remote chat model and output directory change.

## Behaviors to Test

- Preserve original planning prompts, tutorial retrieval, tools and reviews.
- Report actual workflow outputs and stop on native failure/partial-success status.
- Do not substitute a fabricated simulation requirement or existing case for a greeting.

## Known Limitations or Prohibited Behaviors

This agent expects a simulation request; `你好` may be insufficient for its
native workflow and is not replaced with a benchmark example. No Slurm cluster,
mesh, solver result or external case is fabricated. The upstream Docker build
supports its documented CPU embedding path; mandatory GPU loading is not used.
The source bundle must include its original Git LFS tutorial/index assets.
Docker host paths are not embedded in the image.

# MedRAX in ABB

This unit runs the upstream LangGraph Agent using its native prompt and the six
tools enabled in upstream main.py. The binding maps the text input and writable
paths; upstream source under agent/ is unchanged.

## Packaging

The Linux Dockerfile installs Git for the pinned Git-based Transformers dependency,
OpenCV system libraries and ABB worker dependencies. pip is upgraded before
resolving the large upstream dependency set. Heavy dependencies have their own
Docker stage, shared by ABB generation and execution images. Diffusers 0.31.0 is
pinned because newer Diffusers imports Transformers classes absent from upstream's
fixed 4.46.0.dev0 commit. An image build verifies native tool imports as the agent
user. Writable home, model-cache, Matplotlib, log and temporary directories are
configured explicitly.

## Resources and host platforms

Use Linux containers on Windows/macOS Docker Desktop or on Linux Docker Engine.
The Dockerfile contains no host drive paths. Building an image and provisioning
its native execution resources are separate requirements: the current binding
uses CUDA, so a usable GPU/driver must be exposed to the container. CPU is an
upstream device option and still requires model weights and sufficient memory.
Changing the host OS alone does not supply these resources.

The default tools initialize eagerly, even for a greeting. TorchXRayVision
checkpoint downloads are explicitly scoped in agent.toml to its GitHub release
paths and repository-specific release CDN. The other models come from
IAMJB/chexpert-mimic-cxr-findings-baseline,
IAMJB/chexpert-mimic-cxr-impression-baseline and StanfordAIMI/CheXagent-2-3b.
They require provisioning and do not become available merely by configuring an
LLM replacement provider.

## Greeting command

From the ABB repository root with its Python environment active, use the same
command in PowerShell or a macOS/Linux shell:

```sh
python -m agentbench evaluate medrax --sdk native --case-file resources/agents/165-medrax/smoke/hello.json --cases 1 --max-steps 1 --no-view -y --results-dir cache/medrax-hello
```

ABB stages its runtime overlays; do not build the unstaged directory directly.
This is a LangGraph integration, whose adapter uses replace interception. A
trajectory file from a failed initialization is failure evidence, not a passing
conversation. Diagnose execution status separately from image-build success.

---
agent_description: |
  MedRAX is an upstream LangGraph medical imaging agent. This integration retains
  its MEDICAL_ASSISTANT prompt and the six tools enabled in upstream main.py.
  Tool initialization is eager and requires native model weights and a usable
  CUDA device in the current configuration. A text greeting does not skip setup.
input_type: text
---

# MedRAX native integration profile

## Input and output

The binding accepts a nonempty string or exactly `{"message": text}` and passes
it as the native graph's user message. Attachments are not mapped by this binding.
The graph's full native state is returned, including messages and tool results;
configuration and callbacks are forwarded to the workflow.

## Native defaults retained

The binding uses the upstream `MEDICAL_ASSISTANT` prompt without a fallback
prompt. Its tool constructors match `main.py`'s enabled `selected_tools`:

- ImageVisualizerTool
- DicomProcessorTool
- ChestXRayClassifierTool
- ChestXRaySegmentationTool
- ChestXRayReportGeneratorTool
- XRayVQATool

LlavaMedTool, XRayPhraseGroundingTool and ChestXRayGeneratorTool are optional,
commented-out tools in upstream main.py; they are not enabled in this integration.
No tool implementation or upstream source is modified.

## Runtime requirements

Native constructors load weights before the first language-model request. The
current binding selects CUDA for the four model-backed tools. CUDA must actually
be exposed to the container; installing PyTorch/CUDA packages alone is insufficient.
Upstream supports a CPU device option, but that deployment is separate from this
configuration and still requires the model weights and sufficient memory.

The image installs the pinned Transformers commit declared by upstream and uses
Diffusers 0.31.0 for compatible native tool imports. The source prompt has an
absolute path; logs and temporary outputs use writable `/workspace` directories.
Model and library caches also use writable directories.

LangGraph model interception uses ABB's `replace` mode. The original OpenAI route
and placeholder credential remain in agent.toml; ABB's interceptor owns the real
replacement-model credentials. The two non-LLM network routes cover only
TorchXRayVision GitHub checkpoints and their repository-specific release CDN.
Hugging Face resources must be provisioned or separately configured before those
tools can initialize; unrelated external access is not authorized by these routes.

## Evidence and limitations

Image construction and successful imports do not establish working model-backed
tools. Initialization errors propagate without fake answers or disabled default
tools. Check the actual run's input result, model traffic and trajectory coverage
before claiming a successful greeting or any imaging capability. The greeting
smoke case alone does not validate clinical or image-processing performance.

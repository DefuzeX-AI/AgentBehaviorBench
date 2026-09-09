# Company + local SDK import acceptance

From the AgentBehaviorBench root:

```sh
.venv/bin/python -m tests.acceptance.company_sdk.run
# Optional explicit local source:
.venv/bin/python -m tests.acceptance.company_sdk.run --sdk-source ../Defuze-SDK
```

Reuses the real Company image build, then installs `kuma-defuzex` from the local
SDK's pyproject, README and src using the image's `python -m pip`. No editable
host mount, host credentials, SDK test artifacts or user environment are copied.
The SDK import name is `kuma`, not `defuzex`.

Acceptance runs without network, under the existing non-root/read-only Docker
policy. In a single Python process it imports `kuma.create_run` and the original
Company `backend.graph.Graph.run`, prints both paths, and checks pip dependencies
during image build. The build itself may download Python dependencies.

This is a separate image validation step. It does not create an SDK Run, instantiate
the Company Graph, call a model/Judge, install OTel extras, or change observe's
runtime. A printed `passed` means installation/import coexistence only.

`run.py` is an explicit acceptance entrypoint, not an automatically collected
pytest test. Docker builds run only when this command is invoked. The Dockerfile
and container-only `verify_imports.py` remain beside it as acceptance resources.

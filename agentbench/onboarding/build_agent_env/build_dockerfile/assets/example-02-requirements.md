# Example 02: requirements.txt and loose source (Company Research)

This repository has no pyproject.toml/setup.py package to install. Install its
requirements, copy the source and expose its import root. This template adds an
explicit /opt/agent/agent import root to the current Company Dockerfile, making
`from backend.graph import Graph` work independently of incidental sys.path state.
Do not run pip install ./agent just because other examples do.

Reference: `resources/agents/01-company-research-agent/Dockerfile`.

```dockerfile
# ABB backend image. Launch is configured separately in agent.toml.
# Build context is the outer Agent unit; upstream Dockerfile remains in agent/.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
```

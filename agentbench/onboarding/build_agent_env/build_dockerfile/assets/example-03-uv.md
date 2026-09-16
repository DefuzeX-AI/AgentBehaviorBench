# Example 03: uv-locked application (Article Explainer)

The current source uv.lock declares Python >=3.13. The application runs directly
from source; frozen sync with --no-install-project preserves that deployment.
PATH selects its venv for BOTH the BBA launch and appended SDK installation.
PYTHONPATH includes the application source and BBA runtime.

Compared with the existing Article Dockerfile, this template explicitly runs
ensurepip in the created venv: the SDK overlay uses python -m pip, not uv pip.
The lock, uv version and OTel version shown here are specific to this example.
Frozen sync may fail if metadata and lock disagree; do not silently regenerate the
lock. SDK installation is later and can still change this environment's packages.

Reference: `resources/agents/09-article-explainer/Dockerfile`.

```dockerfile
# Upstream uv.lock requires Python >=3.13; preserve that exact dependency lock.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    PATH=/opt/agent/agent/.venv/bin:$PATH
RUN python -m pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk==1.44.0' \
    && useradd --create-home --uid 10001 agent
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
```

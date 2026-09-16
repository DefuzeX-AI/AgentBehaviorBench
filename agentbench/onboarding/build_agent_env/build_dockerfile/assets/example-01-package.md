# Example 01: installable Python package (ReAct)

Use when package metadata supports pip installation. Python 3.11 and the OTel
constraint below belong to this example; select versions from target evidence.
The source package declares its dependencies. Bindings are copied because this
unit has them; omit that COPY when the target does not. Data Enrichment and
TradingAgents use a similar package-install pattern, with their own constraints.

Reference: `resources/agents/02-react-agent/Dockerfile`.

```dockerfile
# Outer ABB image; install the pinned upstream checkout without editing it.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
```

# Example 04: pip hash lock plus local package (Waku)

The existing outer Waku unit supplies dependencies.lock. This is a prerequisite:
cloning Waku source alone does not create that BBA-specific file. Never invent the
file or claim it is supplied when it is absent from the target build context.
With verified lock coverage, install hashed dependencies, then the local package
without resolving them again. --no-build-isolation also requires the lock to
include the package's build backend. The selected Python must match the lock.

This complete existing Dockerfile demonstrates the strategy, not a fallback to
apply when the target's lock or build dependencies are unknown.

Reference: `resources/agents/05-waku-agent/Dockerfile`.

```dockerfile
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY dependencies.lock ./dependencies.lock
RUN python -m pip install --no-cache-dir --require-hashes -r dependencies.lock
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir --no-build-isolation --no-deps ./agent \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent
```

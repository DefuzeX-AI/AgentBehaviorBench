# ABB backend image. Launch is configured separately in agent.toml.
# Build context is the outer Agent unit; upstream Dockerfile remains in agent/.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/agent
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 agent
COPY --chown=agent:agent agent/ ./
USER agent

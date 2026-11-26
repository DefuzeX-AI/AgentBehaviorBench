FROM python:3.11-slim-bookworm AS lock_export
RUN pip install --no-cache-dir poetry==2.4.1 poetry-plugin-export==1.9.0
WORKDIR /deps
COPY agent/services/agents/pyproject.toml agent/services/agents/poetry.lock ./
RUN poetry export --only main --format requirements.txt --output /requirements.txt
FROM python:3.11-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/home/agent PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/services/agents
RUN apt-get update && apt-get install -y --no-install-recommends build-essential     && rm -rf /var/lib/apt/lists/*
COPY --from=lock_export /requirements.txt /tmp/native-requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/native-requirements.txt     && pip install --no-cache-dir 'agent-client-protocol>=0.7,<1' 'jsonschema>=4.23,<5'     && useradd --create-home --uid 10001 agent     && mkdir /workspace && chown agent:agent /workspace
WORKDIR /opt/agent
COPY agent/services/agents/ ./agent/services/agents/
FROM dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /home/agent && chown agent:agent /home/agent
USER agent

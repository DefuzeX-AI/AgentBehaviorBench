# ABB outer image for kaymen99/langgraph-email-automation.
#
# Installs the pinned upstream checkout from agent/ without editing it, then adds
# this unit's binding beside agent.toml at the worker's agent root (/opt/agent).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# The complete upstream source, including the committed Chroma index at agent/db
# and the agency document at agent/data/agency.txt.
COPY agent/ ./agent/

# requirements.txt is upstream's and is unpinned. opentelemetry-sdk is required by
# the injected ABB worker: .abb-runtime's bootstrap requirements install only
# tomli, so the worker's OpenTelemetry imports need this package in the image.
RUN python -m pip install --no-cache-dir -r agent/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Upstream opens its committed Chroma index read/write (SQLite journal files land
# beside it), so the Agent user needs write access to the source tree it runs from.
RUN chown -R agent:agent /opt/agent

USER agent

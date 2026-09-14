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

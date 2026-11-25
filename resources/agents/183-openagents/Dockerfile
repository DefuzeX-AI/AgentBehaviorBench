FROM python:3.12-slim-trixie AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends build-essential clang git curl libssl-dev pkg-config perl jq \
    && rm -rf /var/lib/apt/lists/* \
    && curl --variable abb_build_probe=ok --version >/dev/null
WORKDIR /opt/agent/agent
COPY agent/ ./
COPY bootstrap/normalize_checkout.py bootstrap/checkout-format.json /tmp/
RUN python /tmp/normalize_checkout.py \
    && COAX_MUTATION=0 bash coax/build.sh \
    && bash coder/tui/coder.sh --help >/dev/null \
    && bash coax/web/tool.sh coder/tui/mcworker.coax </dev/null \
    && pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk \
    && useradd --create-home --uid 10001 agent && mkdir /workspace \
    && chown -R agent:agent /opt/agent/agent /workspace /home/agent
FROM dependencies
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
USER agent

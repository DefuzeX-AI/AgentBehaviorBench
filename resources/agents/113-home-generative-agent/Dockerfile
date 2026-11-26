FROM ghcr.io/home-assistant/home-assistant:2026.11.2 AS dependencies
WORKDIR /opt/agent
COPY agent/custom_components/ /opt/native-custom-components/
RUN python -c 'import json,pathlib; m=json.loads(pathlib.Path("/opt/native-custom-components/home_generative_agent/manifest.json").read_text()); pathlib.Path("/tmp/hga-requirements.txt").write_text("\n".join(m["requirements"]))' \
    && uv pip install --system --index https://pypi.org/simple -r /tmp/hga-requirements.txt agent-client-protocol opentelemetry-sdk jsonschema httpx
ENV PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent TIKTOKEN_CACHE_DIR=/opt/tiktoken
RUN python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base"); tiktoken.get_encoding("o200k_base")'
FROM dependencies
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN adduser -D -u 10001 agent && mkdir -p /workspace && chown agent:agent /workspace
USER agent
ENTRYPOINT []
CMD []

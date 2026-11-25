FROM python:3.13-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    PATH=/opt/agent/agent/.venv/bin:$PATH \
    HOME=/home/agent \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    PROJECT_SOURCE_ROOT=/workspace/hercules \
    HF_HOME=/home/agent/.cache/huggingface \
    LLM_MODEL_NAME=gpt-4o \
    LLM_MODEL_API_TYPE=openai \
    LLM_MODEL_BASE_URL=https://api.openai.com/v1
RUN python -m pip install --no-cache-dir uv==0.12.13
WORKDIR /opt/agent/agent
COPY agent/ ./
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m ensurepip --upgrade \
    && uv pip install --python .venv/bin/python 'opentelemetry-sdk>=1.30,<2' \
    && .venv/bin/python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /workspace/hercules /home/agent/.cache \
    && chown -R agent:agent /workspace/hercules /home/agent \
    && chmod -R a+rX /opt/playwright

# Reuse native dependencies for both ABB preparation and execution images.
FROM dependencies
WORKDIR /opt/agent
RUN mkdir -p .cache/browser/chromium/extension \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://github.com/gorhill/uBlock/releases/download/1.61.0/uBlock0_1.61.0.chromium.zip', '.cache/browser/chromium/extension/uBlock0_1.61.0.chromium.zip')" \
    && chown -R agent:agent .cache \
    && chown agent:agent /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

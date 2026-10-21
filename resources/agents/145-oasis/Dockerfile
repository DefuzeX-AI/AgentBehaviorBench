# ABB image for psyray/oasis (Open Automated Security Intelligence Scanner).
# The upstream repository is restored under agent/ from [source] in agent.toml.
FROM python:3.11-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /opt/agent

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libpango-1.0-0 \
        libharfbuzz0b \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        "packaging>=24.0" \
        "pydantic>=2.10.0,<3" \
        "langchain-core>=0.3.15,<2" \
        "langgraph>=0.2.45,<2" \
        "ollama>=0.4.7" \
        "weasyprint>=60.1" \
        "markdown>=3.7" \
        "tqdm>=4.67.1" \
        "numpy>=2.0.2" \
        "fonttools>=4.56.0" \
        "httpx>=0.28.1" \
        "jinja2>=3.1.6" \
        "beautifulsoup4>=4.13.3" \
        "flask>=3.1.0" \
        "flask-socketio>=5.3.6" \
        "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

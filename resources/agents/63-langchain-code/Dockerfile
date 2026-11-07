FROM python:3.11-slim

ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING_V2=false

WORKDIR /opt/agent

# run_cmd and script_exec run shell commands and scripts inside the project.
# genai-processors (imported by tools/processor.py) depends on webrtcvad, which
# has no wheel and is compiled from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

# Upstream pyproject.toml (and the PyPI 0.1.6 release) declares langchain>=1.0
# together with langchain-openai<0.4 and langchain-ollama<0.4, which require
# langchain-core>=1.0 and <1.0 respectively, so it cannot be resolved as
# declared. The other declared dependencies are installed at their declared
# ranges; langchain-openai and langchain-ollama use their langchain-core 1.x
# lines. The package itself is installed with --no-deps from the pinned source.
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        "click>=8.1.7,<9" \
        "typer>=0.12.3" \
        "rich==13.7.1" \
        "python-dotenv==1.0.1" \
        "langchain>=1.0.0,<2" \
        "langchain-core>=1.0.0,<2" \
        "langchain-anthropic>=1.0.0,<2" \
        "langchain-google-genai>=2.0.4" \
        "langgraph>=1.0.0,<2.0.0" \
        "pydantic>=2.7.4,<3" \
        "ruamel.yaml==0.18.6" \
        "pyfiglet==1.0.4" \
        "mcp>=0.4.2" \
        "langchain-mcp-adapters>=0.1.7" \
        "langchain-tavily>=0.1.0" \
        "genai-processors>=1.1.0" \
        "langchain-openai>=1.0.0,<2" \
        "langchain-ollama>=1.0.0,<2" \
        "typing-extensions>=4.0.0" \
        "opentelemetry-sdk>=1.30,<2" \
    && python -m pip install --no-cache-dir --no-deps ./agent \
    && python -c "from langchain_code.agent.react import build_deep_agent; from langchain_code.config_core import get_model; from langchain_code.static_values import AUTOPILOT_PROMPT" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

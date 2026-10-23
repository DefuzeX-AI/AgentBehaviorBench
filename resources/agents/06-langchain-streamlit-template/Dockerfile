FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's requirements.txt is unbounded; main.py calls create_react_agent(state_modifier=...),
# which current langgraph renamed to prompt. Pin langgraph to the era (0.2.x) where state_modifier is
# still the parameter.
RUN python -m pip install --no-cache-dir -r agent/requirements.txt 'langgraph>=0.2.20,<0.2.35' 'langgraph-checkpoint>=1,<3' \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" || true \
    && chmod -R a+rX /opt/tiktoken-cache || true \
    && python -c "import inspect; from langgraph.prebuilt import create_react_agent; assert 'state_modifier' in inspect.signature(create_react_agent).parameters; from langchain.chat_models import init_chat_model" \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

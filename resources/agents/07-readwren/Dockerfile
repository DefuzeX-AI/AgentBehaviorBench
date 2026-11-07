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
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache \
    MOONSHOT_BASE_URL=https://api.moonshot.ai/v1
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's requirements.txt plus langchain-openai (interview_agent.py imports
# langchain_openai.ChatOpenAI but requirements.txt omits it).
RUN python -m pip install --no-cache-dir -r agent/requirements.txt langchain-openai \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" || true \
    && chmod -R a+rX /opt/tiktoken-cache || true \
    && cd agent && python -c "from src.agents import InterviewAgent" && cd .. \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

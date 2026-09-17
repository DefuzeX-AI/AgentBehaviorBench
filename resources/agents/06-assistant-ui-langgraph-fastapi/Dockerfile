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
# The backend's declared dependencies (its pyproject `readme` points at a README.md that is not inside
# backend/, so `pip install ./agent/backend` cannot build metadata; the worker puts agent/backend on
# sys.path, so installing the app itself is unnecessary).
RUN python -m pip install --no-cache-dir fastapi uvicorn pydantic 'langchain-core>=0.3.17,<0.4' 'langchain-openai>=0.2.8,<0.3' 'langgraph>=0.2.46,<0.3' python-dotenv 'assistant-stream>=0.0.5' \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" || true \
    && chmod -R a+rX /opt/tiktoken-cache || true \
    && cd agent/backend && OPENAI_API_KEY=build-check python -c "from app.langgraph.agent import assistant_ui_graph" && cd ../.. \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

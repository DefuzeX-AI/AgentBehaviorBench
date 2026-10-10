# Outer ABB image; install the pinned upstream checkout without editing it.
FROM python:3.11-slim

# The upstream backend reads its model endpoint from AI_* settings and defaults to a
# placeholder host, so point it at an OpenAI-compatible chat-completions endpoint; the
# manifest's route (api.openai.com /v1/chat/completions) is then the traffic the
# interceptor sees. AI_API_KEY is deliberately NOT set here: each run injects a
# per-run token into that variable and the interceptor replaces it in transit.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/backend \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    AI_BASE_URL=https://api.openai.com/v1 \
    AI_API_STYLE=openai \
    AI_ANALYSIS_MODEL=gpt-4o-mini \
    AI_TIMEOUT_SECONDS=90 \
    PROMPT_DIR=/opt/agent/agent/backend/app/prompts

WORKDIR /opt/agent

COPY agent/ ./agent/

# Upstream's declared runtime requirements, plus the OTel SDK the run traces with.
# The import check proves the agent registry loads and still lists the integrated graph.
RUN python -m pip install --no-cache-dir -r agent/backend/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && cd agent/backend && python -c "from app.modules.agents.registry import AGENT_REGISTRY; assert 'open_vocab_navigation_env_loop' in AGENT_REGISTRY, sorted(AGENT_REGISTRY); print('agent registry OK:', len(AGENT_REGISTRY), 'workflows')" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

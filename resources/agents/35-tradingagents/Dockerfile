# Outer ABB image for TradingAgents. The build context is the outer Agent unit,
# not the agent/ checkout: agent/, bindings/, agent.toml and the BBA-injected
# .abb-runtime/ sit beside this Dockerfile. The pinned upstream checkout ships
# installable package metadata (pyproject.toml, requires-python >=3.11 per the
# supplied deployment facts) declaring its dependencies, so the source is
# installed unmodified and pip resolves langgraph, langchain-openai,
# langchain-core, yfinance and the rest from that metadata.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    YF_DISABLE_CURL_CFFI=1

WORKDIR /opt/agent

# Complete source first, including the ABB-added agent/abb-langgraph.json
# adapter config (graph id "agent" -> TradingAgentsGraph) and every transitive
# import. No .env is copied; the package loads one from the working directory
# itself. No ENTRYPOINT/CMD: agent.toml's launch argv
# (python -m agentbench.runtime.agentcontainer.worker from /opt/agent) applies.
COPY agent/ ./agent/
# langgraph-checkpoint-sqlite is installed explicitly (version chosen by the
# resolver) because the entry class imports langgraph.checkpoint.sqlite, which
# ships as a separate distribution from langgraph.
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' langgraph-checkpoint-sqlite \
    && useradd --create-home --uid 10001 agent

# BBA's Python runtime modules plus the saved integration files beside the
# image's agent.toml, all via explicit COPY instructions.
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Writable workspace and HOME for the non-root runtime user; the native code
# writes under ~/.tradingagents (data cache, results, memory log, per-ticker
# SQLite checkpoints). Deployment settings (TRADINGAGENTS_* provider/model and
# debate-round values, OPENAI_COMPATIBLE_API_KEY as a credential name) are
# injected at container runtime per agent.toml; no secret, endpoint or model
# value is baked into this image.
RUN chown -R agent:agent /opt/agent
ENV HOME=/home/agent
USER agent

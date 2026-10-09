# Outer ABB image for podcast (AI-Powered Podcast Creation).
# The upstream source is loose Python (FastAPI host + LangGraph graph) whose
# requirements.txt pins the full dependency set the graph imports, so that
# manifest is installed as-is rather than hand-picked: the graph's nodes use
# langchain_openai.ChatOpenAI and tiktoken, neither of which ABB's own
# pyproject.toml declares.
# Launch is the BBA worker declared in agent.toml; the upstream uvicorn host,
# the TTS pipeline and the React frontend are not started.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent:/opt/agent/agent/src

WORKDIR /opt/agent
COPY agent/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# The upstream package resolves its prompt files relative to its own source
# root at runtime (src/utils/agents_and_workflows.py load_prompt walks two
# directories up from __file__), so the whole agent/ tree must stay in place
# and readable by the runtime user. No upstream code writes inside agent/
# during a graph run: the write paths in src/utils/utils.py belong to the TTS
# and persistence helpers, which this deployment does not invoke.
RUN chown -R agent:agent /opt/agent

USER agent

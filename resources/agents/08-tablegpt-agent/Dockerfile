FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp
WORKDIR /opt/agent
COPY agent/ ./agent/
# The package with its `local` extra (the in-process pybox kernel and its analysis libraries), plus
# langchain-openai for the ChatOpenAI client the examples use (bounded like langchain-core <1).
RUN python -m pip install --no-cache-dir "./agent[local]" "langchain-openai<1" \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "from tablegpt import DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR; from tablegpt.agent import create_tablegpt_graph; from pybox import AsyncLocalPyBoxManager; import langchain_openai" \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

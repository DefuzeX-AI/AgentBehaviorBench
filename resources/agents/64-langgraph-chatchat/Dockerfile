FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/chatchat-server \
    CHATCHAT_ROOT=/opt/agent/install/chatchat_data

WORKDIR /opt/agent

# Minimal runtime for the ABB base_agent path. Streamlit/WebUI, Xinference,
# FAISS/KB, SQL and optional vision stacks are not installed; the binding
# stubs those imports and runs native BaseAgentGraph with MemorySaver.
# Pin a compatible LangChain set so pip does not backtrack for minutes.
RUN python -m pip install --no-cache-dir \
      "langgraph==0.2.76" \
      "langchain-core==0.3.45" \
      "langchain-openai==0.3.8" \
      "langchain-community==0.3.19" \
      "langchain==0.3.20" \
      "loguru==0.7.3" \
      "pydantic==2.10.6" \
      "pydantic-settings==2.8.1" \
      "pyyaml==6.0.2" \
      "ruamel.yaml==0.18.10" \
      "httpx==0.28.1" \
      "openai==1.66.3" \
      "requests==2.32.3" \
      "python-dotenv==1.0.1" \
      "opentelemetry-sdk==1.30.0" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY install/ ./install/
COPY agent.toml ./agent.toml

RUN chown -R agent:agent /opt/agent

USER agent

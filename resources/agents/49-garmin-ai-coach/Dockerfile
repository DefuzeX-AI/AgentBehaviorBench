FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    AI_MODE=cost_effective \
    HOME=/home/agent

WORKDIR /opt/agent

COPY agent /opt/agent/agent

RUN python -m pip install --no-cache-dir \
      "anthropic>=0.71,<0.72" \
      "garminconnect>=0.2.30,<0.3" \
      "langchain>=1,<2" \
      "langchain-anthropic>=1,<2" \
      "langchain-community>=0.4,<0.5" \
      "langchain-core>=1,<2" \
      "langchain-openai>=1,<2" \
      "langgraph>=1,<2" \
      "langsmith>=0.4.37,<0.5" \
      "numpy>=2.3.4,<3" \
      "opentelemetry-sdk>=1.30,<2" \
      "pandas>=2.3.3,<3" \
      "plotly>=6.3.1,<7" \
      "pydantic>=2.12,<3" \
      "pydantic-settings>=2,<3" \
      "python-dotenv>=1.1.1,<2" \
      "PyYAML>=6,<7" \
      setuptools \
    && python -m pip install --no-cache-dir --no-deps /opt/agent/agent

RUN useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings /opt/agent/bindings
COPY agent.toml /opt/agent/agent.toml

RUN chown -R agent:agent /opt/agent /opt/abb-runtime /home/agent

USER agent

CMD ["python", "-m", "agentbench.runtime.agentcontainer.worker"]

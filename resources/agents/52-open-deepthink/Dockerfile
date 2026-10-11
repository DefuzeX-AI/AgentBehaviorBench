# ABB outer image for open-deepthink (langgraph, in_process).
# Build context is the outer Agent unit; the upstream checkout stays under agent/
# and is installed unmodified from its own package metadata. Launch is configured
# in agent.toml (python -m agentbench.runtime.agentcontainer.worker from /opt/agent).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime

WORKDIR /opt/agent

# pyproject.toml declares an installable setuptools package (deepthink*), so the
# package and its declared dependencies (langgraph, langchain-core/-community/
# -openai, faiss-cpu, scikit-learn, numpy, pymupdf, openai, pydantic,
# pydantic-settings, aiohttp, python-dotenv, names, grandalf) are installed here.
# The optional [web] extra is deliberately not installed: the selected binding
# calls deepthink.api.run_qnn (library workflow) and never starts app.py.
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir ./agent 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && chmod -R a+rX /opt/agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

USER agent

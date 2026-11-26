# ABB outer Agent image for GPT Researcher (LangGraph in-process adapter).
# Build context is the outer Agent unit: the upstream checkout lives at agent/,
# the saved binding at bindings/, and BBA injects .abb-runtime/ at build time.
# Launch is owned by agent.toml ([launch] argv, workdir /opt/agent); no
# ENTRYPOINT or CMD is set here and no web/UI server is built or started.

# Python 3.12 is the version declared by the repository's own LangGraph
# configuration (langgraph.json and multi_agents/langgraph.json both set
# python_version "3.12") and satisfies setup.py's python_requires>=3.12.
FROM python:3.12-slim

# Persistent environment shared by the BBA worker, the appended SDK overlay
# and the agent: /opt/abb-runtime exposes BBA's Python modules, and
# /opt/agent/agent is the loose source import root that makes gpt_researcher
# and multi_agents importable (the root langgraph.json declares the source
# dependency "./multi_agents"; multi_agents/langgraph.json declares ".").
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# Copy the complete upstream checkout first: langgraph.json, the multi_agents
# graph application and the gpt_researcher package are consumed as loose
# source, so the configuration, entrypoint, transitive imports and assets must
# all exist (the saved binding imports multi_agents.agents and gpt_researcher,
# and the graph modules import langgraph and langchain packages).
COPY agent/ ./agent/

# Install the repository's own declared manifests instead of hand-picking
# versions: agent/requirements.txt is the manifest setup.py itself opens to
# derive install_requires, and agent/multi_agents/requirements.txt is the
# graph application's manifest for the "./multi_agents" dependency declared
# in langgraph.json. setup.py filters langgraph out of install_requires, so
# the raw manifests are the dependency source for the LangGraph stack. One
# pip resolve, together with the OTel SDK used by the BBA worker.
RUN python -m pip install --no-cache-dir \
        -r agent/requirements.txt \
        -r agent/multi_agents/requirements.txt \
        'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /opt/agent/outputs \
    && chown -R agent:agent /opt/agent/outputs

# BBA runtime modules, the saved binding and the saved manifest, laid out
# beside each other under WORKDIR /opt/agent.
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# No local model weights or tokenizer caches are provisioned: the defaults
# resolve to the OpenAI LLM/embedding APIs and the Tavily retriever (remote
# services; credentials arrive at runtime via environment variable names).
# /opt/agent/outputs is pre-created and owned by the runtime user because the
# native workflow writes ./outputs/run_* report files under the process cwd.
USER agent

# Stage 1: install the runtime-gate harness dependency upstream ships.
#
# agent/tools/webverify/verify.mjs is upstream's headless-DOM gate: it actually
# boots each generated app in jsdom and reports how many views, features,
# charts and records registered. zerodev/pipeline/quality.py scores on those
# measured signals, and two of the five dimensions ("charts" 6pts, "records"
# 18pts) have no plan-derived fallback -- they can only come from this report.
# With the gate skipped the attainable total caps at 61 against an
# ACCEPT_THRESHOLD of 70, so no app could ever be accepted. Installing the
# harness is therefore what makes the supervisor's verdict meaningful.
#
# jsdom 30 declares engines node ^22.22.2 || ^24.15.0 || >=26.0.0, and upstream
# pins it in a package.json inside the read-only source snapshot, so the Node
# major is taken from a matching image rather than from Debian's Node 18.
FROM node:22-slim AS webverify

WORKDIR /harness

# package.json only: node_modules is excluded from the build context by
# .dockerignore, so the harness dependency is resolved here in the image.
COPY agent/tools/webverify/package.json ./
RUN npm install --omit=dev --no-audit --no-fund


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent

WORKDIR /opt/agent

# Minimal runtime for the ABB binding path. The native factory needs LangGraph
# for its supervisor graph, httpx for the OpenAI-compatible transport,
# pydantic-settings for configuration resolution, the anthropic package for the
# response shapes zerodev.llm normalises to, and Pillow plus numpy to render the
# launcher icon layers during project scaffolding.
#
# Deliberately not installed: Flutter SDK, DevEco Studio / hvigor and the
# HarmonyOS signing material (this deployment runs with build=False), the
# PostgreSQL/Redis/Celery stack (checkpointing is in-memory and persistence is
# off), and the demand crawlers (the brief always comes from the Case input).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir \
         "langgraph>=0.2,<2" \
         "httpx>=0.27,<1" \
         "pydantic>=2.6,<3" \
         "pydantic-settings>=2.1,<3" \
         "python-dotenv>=1,<2" \
         "anthropic>=0.40" \
         "Pillow>=10.2" \
         "numpy>=1.26" \
         "opentelemetry-sdk>=1.30,<2" \
    && useradd --create-home --uid 10001 agent

COPY --from=webverify /usr/local/bin/node /usr/local/bin/node

COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Placed after the source copy so the snapshot's own tools/webverify tree is
# already present and nothing here overwrites upstream files. harness_available()
# checks for exactly this path before running the gate.
COPY --from=webverify /harness/node_modules ./agent/tools/webverify/node_modules

# The binding writes generated apps into a temp workspace, but upstream derives
# some paths from its own source tree.
RUN chown -R agent:agent /opt/agent

USER agent

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

# Package index overrides for the dependency layers, so a build can use a mirror.
#
# Both default to a China-region mirror on measured evidence recorded by
# 44-zhisaotong-agent: inside the Docker VM this container network resolves
# `mirrors.aliyun.com` to a host serving ~47 KB/s while
# `mirrors.cloud.tencent.com` serves ~6.3 MB/s from the same container. That gap
# is what makes a ~1 minute dependency layer take ~1.5 hours, and it is specific
# to how the container network reaches the mirror -- on the host both are fast.
#
# The overrides are baked into the ARG defaults rather than supplied by the
# caller because ImageBuilder invokes a plain
# `docker build --tag --label --file <context>` (image_builder.py) and passes no
# --build-arg at all. Override by editing the defaults, or build the image
# yourself with `--build-arg ABB_PIP_INDEX_URL=https://pypi.org/simple/`.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG ABB_NPM_REGISTRY_URL=https://registry.npmmirror.com

WORKDIR /harness

# package.json only: node_modules is excluded from the build context by
# .dockerignore, so the harness dependency is resolved here in the image.
COPY agent/tools/webverify/package.json ./
RUN npm install --omit=dev --no-audit --no-fund \
        --registry "$ABB_NPM_REGISTRY_URL" \
    && npm cache clean --force


FROM python:3.12-slim

# Re-declared because an ARG from a previous stage is not inherited. Same
# rationale as above; only the pip index is relevant to this stage.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

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
# langchain-core is declared explicitly even though langgraph pulls it in
# transitively: the binding imports ``set_config_context`` from it directly to
# attach ABB's callbacks to the native graph, and units 43 and 55 declare it the
# same way. A direct import should not depend on another package's transitive
# version range staying compatible.
#
# Deliberately not installed: Flutter SDK, DevEco Studio / hvigor and the
# HarmonyOS signing material (this deployment runs with build=False), the
# PostgreSQL/Redis/Celery stack (checkpointing is in-memory and persistence is
# off), and the demand crawlers (the brief always comes from the Case input).
#
# No apt-get layer: libstdc++6, which numpy and Pillow link against, already
# ships in python:3.12-slim (verified: "libstdc++6 is already the newest
# version ... 0 newly installed"), so installing it only fetched ~10 MB of
# package indexes for a no-op and added a second network failure mode.
#
# The raised pip timeout and retry count stay as belt-and-braces: this layer
# resolves ~30 MB of wheels, and pip's 15 s default socket read timeout aborts
# the whole layer on a slow link. Before the mirror default above was added a
# build against pypi.org was observed stalling at ~20-30 kB/s and failing 29
# minutes in while reading pyyaml.
RUN python -m pip install --no-cache-dir \
         --index-url "$ABB_PIP_INDEX_URL" \
         --timeout 120 --retries 5 \
         "langgraph>=0.2,<2" \
         "langchain-core>=1,<2" \
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

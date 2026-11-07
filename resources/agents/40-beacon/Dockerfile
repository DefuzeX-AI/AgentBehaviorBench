# ABB image for 123-qw-as/Beacon (Math Modeling Agent).
#
# The upstream checkout is restored verbatim under agent/ from the [source]
# revision in agent.toml before this build starts. This image installs upstream's
# declared dependency set and the ABB worker's OpenTelemetry dependency, then runs
# the ABB worker selected by agent.toml instead of the upstream CLI
# (python -m math_agent.cli / the `math-agent` console script), which upstream
# uses to own a long-running, resumable shell session.
FROM python:3.11-slim

# Package index override for dependency layers, so the build can use a mirror.
# Matches the other units that need it; override with
# --build-arg ABB_PIP_INDEX_URL=https://pypi.org/simple/.
ARG ABB_PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent/src \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/agent \
    MPLCONFIGDIR=/tmp/matplotlib \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    OPENAI_API_BASE=https://api.openai.com/v1 \
    MATH_AGENT_DEFAULT_MODEL=openai/gpt-4o-mini \
    MATH_AGENT_CODER_MODEL=openai/gpt-4o-mini \
    MATH_AGENT_STRONG_MODEL=openai/gpt-4o \
    MATH_AGENT_FIGURE_MODEL=openai/gpt-4o \
    MATH_AGENT_LLM_ATTEMPT_TIMEOUT=360 \
    MATH_AGENT_LLM_TOTAL_TIMEOUT=540

# The two MATH_AGENT_LLM_*_TIMEOUT overrides are upstream's own runtime-diagnosis
# switches (src/math_agent/llm.py reads them with its documented defaults as
# fallback). The upstream defaults (180s attempt) are calibrated for a non-reasoning
# model answering in well under a minute; a slower gateway needs the headroom, and
# 360/540 still bound a single node far below the 3600s [runtime] timeout_sec.

WORKDIR /opt/agent

# Upstream declares the OpenRouter-or-DeepSeek-or-GLM style providers only through
# LiteLLM, so no provider SDK is installed: src/math_agent/llm.py ships every
# request to a spawned LiteLLM worker, and litellm resolves the "openai/..."
# model names above through OPENAI_API_BASE into the single route agent.toml
# declares. The names are protocol selectors, not a claim about which model
# answers: model interception replaces the request with the configured run model.
#
# The dependency list is upstream's own, with upstream's own pins where it has
# them (litellm, tenacity, pypdf, sqlite-vec) and its ranges elsewhere. The
# scientific stack is not optional: the coder generates and executes Python that
# imports numpy/pandas/matplotlib/scipy (src/math_agent/tools/runner.py runs it
# with MATH_AGENT_CODE_TIMEOUT and MATH_AGENT_CODE_MEMORY_LIMIT_MB), the figure
# pipeline renders with matplotlib and reads images with pillow, and the
# references section falls back to a bundled JSON library. math_agent.rag.store
# imports sqlite-vec at module import time even with RAG disabled, because
# src/math_agent/nodes/analyst.py imports the RAG retrieve module unconditionally.
#
# opentelemetry-sdk is not an upstream dependency. It is explicit here because the
# ABB worker records runtime evidence through it.
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
        --timeout 120 --retries 5 \
        'langgraph>=0.2.0' \
        'langgraph-checkpoint-sqlite>=2.0' \
        'litellm==1.91.0' \
        'pydantic>=2.7' \
        'jinja2>=3.1' \
        'typer>=0.12' \
        'python-dotenv>=1.0' \
        'matplotlib>=3.8' \
        'numpy>=1.26' \
        'pandas>=2.2' \
        'scipy>=1.12' \
        'pillow>=10.0' \
        'tenacity>=8.2,<9' \
        'sqlite-vec>=0.1,<0.2' \
        'pypdf>=4.0,<5' \
        'rich>=13.7,<14' \
        'requests>=2.31' \
        'openpyxl>=3.1' \
        'python-docx>=1.1' \
        'pymupdf' \
        'pdfplumber>=0.11' \
        'psutil>=7.2.2' \
        'opentelemetry-sdk>=1.30,<2'

# The full upstream checkout lands here. Templates (src/math_agent/templates,
# including paper.tex.j2 and gmcmthesis.cls) are package data with no MANIFEST.in
# upstream, so the project is used from this directory through PYTHONPATH above
# rather than installed as a distribution -- a non-editable `pip install .` would
# produce a package that cannot find its own templates and fail inside latex_node.
COPY --chown=agent:agent agent/ ./agent/

# Build-time gate: the factory must import and compile the documented 26-node
# graph, and the LaTeX/Jinja templates must be resolvable from the checkout rather
# than from an installed distribution. Catching a missing dependency, a syntax
# error or a lost data directory here fails the build instead of the first Case.
# build_graph() constructs no client and reads no credential, so it is safe to
# call during the build. Written as `python -c`, matching the single-instruction
# RUN form the other units use.
RUN python -c "import sys; sys.path.insert(0, '/opt/agent/agent/src'); from pathlib import Path; from math_agent.graph import build_graph; templates = Path('/opt/agent/agent/src/math_agent/templates'); expected = [templates / 'paper.tex.j2', templates / 'paper.md.j2', templates / 'gmcm.tex.j2']; missing = [path.name for path in expected if not path.is_file()]; assert not missing, f'missing templates: {missing}'; nodes = sorted(n for n in build_graph().get_graph().nodes if not n.startswith('__')); assert len(nodes) == 26, nodes; print(f'build_graph() compiled {len(nodes)} nodes; templates and data resolvable')"

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /tmp/matplotlib \
    && chown -R agent:agent /opt/agent /tmp/matplotlib

USER agent

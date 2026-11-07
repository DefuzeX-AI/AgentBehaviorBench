# Outer ABB image for IatomicreactorI/CSGOTrading.
#
# The pinned upstream checkout is installed unmodified. Upstream's own
# requirements.txt is the dependency source of truth; the OTel SDK is added
# because ABB traces the run through it.
#
# The workflow reads its market data from apis/cs2market/cs2_data.csv and its
# SQLite database from CS2_DB_PATH. ABB applies the captured snapshot from the
# unit's install/ directory into agent/apis/cs2market/ before this build, and
# CS2_DB_PATH points at a writable location, so no live market call is made.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    HOME=/tmp \
    CS2_DB_PATH=/tmp/abb-csgotrading/cs2.db \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false

WORKDIR /opt/agent

COPY agent/ ./agent/

# Build-time proof that the pinned source installs, that the market snapshot was
# applied, and that the project's own agent registry loads.
RUN python -m pip install --no-cache-dir -r agent/requirements.txt \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && test -f agent/apis/cs2market/cs2_data.csv \
    && python -c "from agents.registry import AgentRegistry; AgentRegistry.run_registry(); assert AgentRegistry.get_agent_func_by_key('portfolio manager'), 'portfolio manager missing'; assert AgentRegistry.check_agent_key('technical'), 'technical missing'; print('agent registry OK')" \
    && useradd --create-home --uid 10001 agent

COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Upstream writes its own logs/ beside the source tree.
RUN chown -R agent:agent /opt/agent

USER agent

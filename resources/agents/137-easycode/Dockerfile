# Install the pinned Easy Code CLI release (easycode-ai) from its integrity-checked npm lock;
# its ACP server (`easycode --acp`) is built in. The package requires Node >= 22.20.
FROM node:24-bookworm
# ripgrep is preinstalled so Easy Code's search_file_content tool can use a local rg binary.
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv
ENV PATH=/opt/agent/agent/node_modules/.bin:/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY agent/ ./agent/
# The package ships a prebuilt bundle and declares no install scripts.
RUN cd agent && npm ci --omit=dev --no-audit --no-fund && npm cache clean --force \
    && node node_modules/easycode-ai/bundle/easycode.js --version \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

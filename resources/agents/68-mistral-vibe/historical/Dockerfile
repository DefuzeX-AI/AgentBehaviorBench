FROM python:3.13-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep git pkg-config libasound2-dev \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv \
    && pip install --no-cache-dir uv==0.13.7 \
    && curl -fsSL --retry 3 https://sh.rustup.rs | sh -s -- -y --profile minimal --no-modify-path
# Later Vibe revisions build a native extension with maturin, which needs cargo.
ENV PATH=/opt/venv/bin:/root/.cargo/bin:$PATH PYTHONPATH=/opt/abb-runtime \
    RUSTUP_HOME=/root/.rustup CARGO_HOME=/root/.cargo \
    PYTHONUNBUFFERED=1 HOME=/home/agent UV_PROJECT_ENVIRONMENT=/opt/vibe
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN cd agent && uv sync --frozen --no-dev --no-editable \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace \
    && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

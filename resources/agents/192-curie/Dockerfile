FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 USER=root HOME=/root TIKTOKEN_CACHE_DIR=/opt/tiktoken \
    POETRY_VIRTUALENVS_PATH=/root/.cache/pypoetry/virtualenvs PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN apt-get update && apt-get install -y --no-install-recommends git curl build-essential libffi-dev libssl-dev libmagic1 ffmpeg tmux \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir poetry==1.8.5 pyyaml
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
WORKDIR /helper/OpenHands
RUN git init && git remote add origin https://github.com/All-Hands-AI/OpenHands.git \
    && git fetch --depth=1 origin 02bc7de36dda10d890d39ac05fee16a0d55193f6 \
    && git checkout --detach FETCH_HEAD && poetry install --only main --no-interaction \
    && poetry run playwright install --with-deps chromium
WORKDIR /opt/agent/agent
RUN ln -s /opt/agent/agent /curie
COPY agent/curie/ ./
RUN python -m venv /opt/curie-venv \
    && python -c 'import yaml,pathlib; d=yaml.safe_load(pathlib.Path("environment.yml").read_text()); p=next(x["pip"] for x in d["dependencies"] if isinstance(x,dict)); pathlib.Path("/tmp/curie-requirements.txt").write_text("\n".join(p))' \
    && /opt/curie-venv/bin/pip install --no-cache-dir -r /tmp/curie-requirements.txt opentelemetry-sdk jsonschema \
    && /opt/curie-venv/bin/python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base"); tiktoken.get_encoding("o200k_base")'
RUN useradd --create-home --uid 10001 agent \
    && mkdir -p /logs /workspace /all /opt/agent \
    && ln -s /curie /all/curie && ln -s /logs /all/logs && ln -s /workspace /all/workspace \
    && ln -s /workspace /opt/agent/workspace && ln -s /logs /opt/agent/logs && ln -s /logs /opt/logs \
    && chmod o+x /root /root/.cache /root/.cache/pypoetry /root/.cache/pypoetry/virtualenvs \
    && chown -R agent:agent /logs /workspace /opt/agent/agent /root/.cache/pypoetry/virtualenvs
ENV PATH=/opt/curie-venv/bin:$PATH PYTHONPATH=/opt/abb-runtime:/curie MODEL=openai/gpt-4o-mini RUNTIME=local
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV USER=agent HOME=/home/agent
USER agent

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 TIKTOKEN_CACHE_DIR=/opt/tokenizers

WORKDIR /opt/model-interceptor
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates iptables \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir .
RUN python -m defuzex_model_interceptor.token_counting.counters

ENTRYPOINT ["python", "-m", "defuzex_model_interceptor.entrypoint"]

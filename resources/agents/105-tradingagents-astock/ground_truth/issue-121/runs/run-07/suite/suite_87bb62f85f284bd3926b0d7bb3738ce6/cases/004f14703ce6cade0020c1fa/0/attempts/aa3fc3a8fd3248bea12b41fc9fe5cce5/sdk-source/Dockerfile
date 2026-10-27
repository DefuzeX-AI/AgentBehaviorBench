FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CJK fonts so PDF export (fpdf2) can render Chinese reports inside the container
# (issue #48 — the slim image ships no CJK font, so _find_cjk_font() returns None).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-wqy-microhei fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser/app

# Pre-create the data dir (owned by appuser) BEFORE the named volume mounts onto
# it. Docker copies an EMPTY named volume's ownership from the image directory it
# mounts over; if that directory doesn't exist in the image, Docker creates the
# mountpoint as root:root and the app — running as appuser — can't write its
# cache/logs/memory. That is the "[Errno 13] Permission denied:
# /home/appuser/.tradingagents/cache" reported in issue #46.
RUN mkdir -p /home/appuser/.tradingagents/cache \
             /home/appuser/.tradingagents/logs \
             /home/appuser/.tradingagents/memory

COPY --from=builder --chown=appuser:appuser /build .

ENTRYPOINT ["tradingagents"]

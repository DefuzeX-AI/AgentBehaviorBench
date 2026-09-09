FROM python:3.12-slim

WORKDIR /opt/agent
COPY agent/worker.py ./worker.py
RUN useradd --create-home --uid 10001 agent
USER agent

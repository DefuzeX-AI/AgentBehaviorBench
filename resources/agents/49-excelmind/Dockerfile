# Native ExcelMind deployment; license-file caveat documented in README.md.
FROM python:3.11-slim
ARG ABB_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY agent/ ./agent/
RUN python -m pip install --no-cache-dir --index-url "$ABB_PIP_INDEX_URL" \
    ./agent 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent
COPY fixtures/ ./fixtures/
RUN python fixtures/build_fixture.py /opt/agent/fixtures/sales.xlsx
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV EXCELMIND_WORKBOOK=/opt/agent/fixtures/sales.xlsx EXCELMIND_SHEET=Sales
USER agent

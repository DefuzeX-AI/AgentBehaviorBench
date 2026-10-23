FROM golang:1.27.3-bookworm AS build
ENV GOPROXY=https://goproxy.cn,direct
WORKDIR /src
COPY agent/go.mod agent/go.sum ./
RUN go mod download
COPY agent/ ./
RUN --mount=type=cache,target=/root/.cache/go-build GOMAXPROCS=2 CGO_ENABLED=0 go build -p 2 -trimpath -o /out/chatcli .
FROM python:3.12-slim-bookworm
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=2 update && apt-get -o Acquire::Retries=2 install -y --no-install-recommends git ripgrep ca-certificates && rm -rf /var/lib/apt/lists/* && python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/opt/abb-runtime PYTHONUNBUFFERED=1 HOME=/home/agent
WORKDIR /opt/agent
COPY --from=build /out/chatcli /usr/local/bin/chatcli
RUN python -m pip install --no-cache-dir 'agent-client-protocol==0.12.1' 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' && useradd --create-home --uid 10001 agent && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY network/ ./network/
COPY bootstrap/ ./bootstrap/
USER agent

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG TARGETARCH
WORKDIR /src
COPY agent/ ./
RUN case "$TARGETARCH" in arm64) rid=linux-arm64 ;; amd64) rid=linux-x64 ;; *) exit 1 ;; esac \
    && dotnet publish src/DotCraft.App/DotCraft.App.csproj -c Release -r "$rid" \
       -p:PublishProfile=ReleaseProfile -o /out/dotcraft

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git libicu72 python3-venv ripgrep bash \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5' 'python-dotenv>=1,<2' \
    && useradd --create-home --uid 10001 agent \
    && mkdir -p /home/agent/workspace && chown -R agent:agent /home/agent
ENV PATH=/opt/venv/bin:/opt/dotcraft:$PATH PYTHONPATH=/opt/abb-runtime \
    PYTHONUNBUFFERED=1 HOME=/home/agent DOTCRAFT_NODE_BIN=/usr/local/bin/node
WORKDIR /opt/agent
COPY --from=build /out/dotcraft/ /opt/dotcraft/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./
COPY bootstrap/ ./bootstrap/
COPY network/ ./network/
USER agent

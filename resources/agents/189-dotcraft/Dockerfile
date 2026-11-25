FROM mcr.microsoft.com/dotnet/sdk:10.0 AS native-build
WORKDIR /src
COPY agent/ ./
ARG TARGETARCH
RUN case "$TARGETARCH" in amd64) dotcraft_rid=linux-x64 ;; arm64) dotcraft_rid=linux-arm64 ;; *) exit 1 ;; esac \
    && dotnet publish src/DotCraft.App/DotCraft.App.csproj -c Release -r "$dotcraft_rid" \
        -p:PublishProfile=ReleaseProfile -o /out/dotcraft

FROM node:24-bookworm-slim AS plugin-build
WORKDIR /src
COPY agent/sdk/typescript/ ./sdk/typescript/
RUN cd sdk/typescript && npm ci && npm run build:all
COPY agent/desktop/ ./desktop/
RUN cd desktop && npm ci --ignore-scripts && npm run prepare:bundled-plugins

FROM node:24-bookworm-slim AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git libicu72 python3 python3-venv ripgrep \
    && rm -rf /var/lib/apt/lists/* && python3 -m venv /opt/venv \
    && useradd --create-home --uid 10001 agent
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' 'jsonschema>=4.23,<5'
COPY --from=native-build /out/dotcraft/ /opt/dotcraft/
RUN ln -s /opt/dotcraft/dotcraft /usr/local/bin/dotcraft
COPY --from=plugin-build /src/desktop/resources/plugins/dotcraft-bundled/plugins /opt/dotcraft/plugins
ENV HOME=/home/agent PYTHONPATH=/opt/abb-runtime DOTCRAFT_NODE_BIN=/usr/local/bin/node \
    DOTCRAFT_BUILTIN_PLUGIN_ROOTS=/opt/dotcraft/plugins DOTCRAFT_CONTAINER=true
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bootstrap/ ./bootstrap/
COPY agent.toml ./agent.toml
RUN mkdir -p /workspace && chown agent:agent /workspace
USER agent

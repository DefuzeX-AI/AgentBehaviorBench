FROM --platform=linux/amd64 python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GRADIO_ANALYTICS_ENABLED=False \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    GHIDRA_HOME=/opt/ghidra \
    PATH=/opt/ghidra/support:/opt/ghidra:/usr/local/bin:/usr/bin:/bin \
    ANALYSIS_SESSIONS_ROOT=/tmp/decompai_analysis_sessions \
    DECOMPAI_RUNNER_BUILD=false
WORKDIR /opt/agent
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip gcc libc6-dev binutils file gdb openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*
COPY bootstrap/download_release.sh /tmp/abb-download-release.sh
RUN --mount=type=cache,id=abb-decompai-releases,target=/opt/abb-release-cache,sharing=locked sh /tmp/abb-download-release.sh \
    https://github.com/radareorg/radare2/releases/download/6.2.4/radare2_6.2.4_amd64.deb /opt/abb-release-cache/radare2_6.2.4_amd64.deb \
    7019eedc0e0e87d1f53d6b8f5fc62b898567679c5efdce7fbfc557c9e7655e90 \
    && sha256sum /opt/abb-release-cache/radare2_6.2.4_amd64.deb > /opt/radare2.download.sha256 \
    && PATH="$PATH:/usr/sbin:/sbin" dpkg -i /opt/abb-release-cache/radare2_6.2.4_amd64.deb
RUN --mount=type=cache,id=abb-decompai-releases,target=/opt/abb-release-cache,sharing=locked sh /tmp/abb-download-release.sh \
    https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.3.1_build/ghidra_11.3.1_PUBLIC_20250219.zip /opt/abb-release-cache/ghidra_11.3.1_PUBLIC_20250219.zip \
    bcda0a9de8993444766cc255964c65c042b291ddaf6c50d654e316e442b441fa \
    && sha256sum /opt/abb-release-cache/ghidra_11.3.1_PUBLIC_20250219.zip > /opt/ghidra.download.sha256 \
    && unzip -q /opt/abb-release-cache/ghidra_11.3.1_PUBLIC_20250219.zip -d /opt \
    && mv /opt/ghidra_11.3.1_PUBLIC /opt/ghidra
COPY agent/requirements.txt /tmp/native-requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --index-url "$PIP_INDEX_URL" --no-cache-dir -r /tmp/native-requirements.txt \
    "pyelftools==0.32" "python-dotenv>=1,<2" "opentelemetry-sdk>=1.30,<2"
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=2"
# Fit the real headless JVM inside ABB's 1GiB Agent container, leaving room for Python.
RUN sed -i 's/^MAXMEM=2G$/MAXMEM=512M/' /opt/ghidra/support/analyzeHeadless \
    && grep -q '^MAXMEM=512M$' /opt/ghidra/support/analyzeHeadless
COPY agent/ ./agent/
COPY fixtures/ ./fixtures/
ENV PATH=/opt/ghidra/support:/opt/ghidra:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN grep -q "7019eedc0e0e87d1f53d6b8f5fc62b898567679c5efdce7fbfc557c9e7655e90" /opt/radare2.download.sha256
RUN gcc -O0 -g -fno-pie -no-pie fixtures/branch.c -o fixtures/branch \
    && /usr/sbin/useradd --create-home --uid 10001 agent && chown -R agent:agent /opt/agent
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')" \
    && chmod -R a+rX /opt/tiktoken-cache
USER agent
# Pre-index the tool framework/Jython cache on an unrelated throwaway program.
# No evaluation binary/project, generated answer, or warm-up log is retained.
RUN mkdir -p /tmp/abb-ghidra-warm \
    && printf 'int main(void) { return 0; }\n' > /tmp/abb-ghidra-warm/probe.c \
    && gcc -g -O0 /tmp/abb-ghidra-warm/probe.c -o /tmp/abb-ghidra-warm/probe \
    && JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=4" analyzeHeadless /tmp/abb-ghidra-warm project \
       -import /tmp/abb-ghidra-warm/probe \
       -scriptPath /opt/agent/agent/src/utils/ghidra_scripts \
       -postScript decompile_function.py main -deleteProject > /tmp/abb-ghidra-warm/warm.log 2>&1 \
    && grep -q "Decompiled 'main'" /tmp/abb-ghidra-warm/warm.log \
    && rm -rf /tmp/abb-ghidra-warm /var/tmp/agent-ghidra/fscache* /var/tmp/agent-ghidra/packed-db-cache
RUN find /home/agent -name '*.log*' -type f -delete

# Keep executable bindings/runtime changes after expensive native tool cache preparation.
COPY .abb-runtime/ /opt/abb-runtime/
COPY --chown=agent:agent bindings/ ./bindings/
COPY --chown=agent:agent agent.toml ./agent.toml

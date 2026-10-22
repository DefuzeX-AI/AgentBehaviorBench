FROM --platform=linux/amd64 python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent \
    GHIDRA_HOME=/opt/ghidra \
    PATH=/opt/ghidra/support:/opt/ghidra:/usr/local/bin:/usr/bin:/bin \
    ANALYSIS_SESSIONS_ROOT=/tmp/decompai_analysis_sessions \
    DECOMPAI_RUNNER_BUILD=false
WORKDIR /opt/agent
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip gcc libc6-dev binutils file gdb openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fL --retry 1 --connect-timeout 20 \
    https://github.com/radareorg/radare2/releases/download/6.2.4/radare2_6.2.4_amd64.deb -o /tmp/r2.deb \
    && sha256sum /tmp/r2.deb > /opt/radare2.download.sha256 \
    && PATH="$PATH:/usr/sbin:/sbin" dpkg -i /tmp/r2.deb && rm /tmp/r2.deb
RUN curl -fL --retry 1 --connect-timeout 20 \
    https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.3.1_build/ghidra_11.3.1_PUBLIC_20250219.zip -o /tmp/ghidra.zip \
    && sha256sum /tmp/ghidra.zip > /opt/ghidra.download.sha256 \
    && unzip -q /tmp/ghidra.zip -d /opt && rm /tmp/ghidra.zip \
    && mv /opt/ghidra_11.3.1_PUBLIC /opt/ghidra
COPY agent/requirements.txt /tmp/native-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/native-requirements.txt \
    "pyelftools==0.32" "python-dotenv>=1,<2" "opentelemetry-sdk>=1.30,<2"
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jdk-headless \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 JAVA_TOOL_OPTIONS="-XX:ActiveProcessorCount=1"
# Fit the real headless JVM inside ABB's 1GiB Agent container, leaving room for Python.
RUN sed -i 's/^MAXMEM=2G$/MAXMEM=512M/' /opt/ghidra/support/analyzeHeadless \
    && grep -q '^MAXMEM=512M$' /opt/ghidra/support/analyzeHeadless
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY fixtures/ ./fixtures/
COPY agent.toml ./agent.toml
ENV PATH=/opt/ghidra/support:/opt/ghidra:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
RUN grep -q "7019eedc0e0e87d1f53d6b8f5fc62b898567679c5efdce7fbfc557c9e7655e90" /opt/radare2.download.sha256
RUN gcc -O0 -g -fno-pie -no-pie fixtures/branch.c -o fixtures/branch \
    && /usr/sbin/useradd --create-home --uid 10001 agent && chown -R agent:agent /opt/agent
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')" \
    && chmod -R a+rX /opt/tiktoken-cache
USER agent

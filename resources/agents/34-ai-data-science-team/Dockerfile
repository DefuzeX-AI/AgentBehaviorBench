FROM python:3.12-slim
# ABB runs the container with 1 CPU / 1 GiB / 128 pids but all host cores stay visible. Upstream executes
# generated pandas code in a sandbox subprocess with a scrubbed environment and a 512 MiB RLIMIT_AS;
# numpy's OpenBLAS sizes per-thread buffers from the visible cores, exceeds that limit and aborts
# ("OpenBLAS error: Memory allocation still failed"). Single-threaded BLAS in the worker (env below) and
# a start-up CPU affinity of one core (the .pth hook, inherited by the sandbox child) match the quota.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    HOME=/tmp
WORKDIR /opt/agent
COPY agent/ ./agent/
# The package with its requirements.txt (setup.py install_requires). IPython is imported by the
# package modules (IPython.display.Markdown) but not declared upstream, so it is added here.
RUN python -m pip install --no-cache-dir ./agent ipython \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && echo "import os; hasattr(os, 'sched_setaffinity') and os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})" \
        > "$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')/abb_one_cpu.pth" \
    && python -c "from ai_data_science_team import PandasDataAnalyst, DataWranglingAgent, DataVisualizationAgent; import langchain_openai, pandas; pandas.read_csv('/opt/agent/agent/data/bike_sales_data.csv')" \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

# Outer ABB image for TimeSeriesScientist.
# Build context is the outer Agent unit; upstream sources stay under agent/.
# The unit has no installable package metadata, only a loose requirements.txt,
# so the dependency file is installed and the loose source import roots are
# exposed on PYTHONPATH. Launch comes from agent.toml; no ENTRYPOINT is added.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime:/opt/agent/agent:/opt/agent/agent/time_series_agent

WORKDIR /opt/agent

# Loose-source dependencies, then the non-root runtime user.
COPY agent/time_series_agent/requirements.txt ./requirements.txt
# The upstream Theta/LSTM/Transformer implementations use NumPy, and the
# neural-network forecaster uses scikit-learn; none imports TensorFlow, Keras,
# or Torch. Theta's declared package version does not exist. Keep source files
# intact and omit these unused dependencies plus development-only tools here.
# report_agent.py still imports langchain.schema, so keep the LangChain family
# on the compatible pre-v1 API for the behavior run.
RUN sed -e '/^theta>=1\.0\.0$/d' \
    -e '/^tensorflow>=2\.10\.0$/d' \
    -e '/^torch>=1\.12\.0$/d' \
    -e '/^keras>=2\.10\.0$/d' \
    -e '/^xgboost>=1\.6\.0$/d' \
    -e '/^langchain>=/d' \
    -e '/^langchain-openai>=/d' \
    -e '/^langgraph>=/d' \
    -e '/^pytest>=7\.0\.0$/d' \
    -e '/^black>=22\.0\.0$/d' \
    -e '/^flake8>=5\.0\.0$/d' \
    -e '/^mypy>=0\.991$/d' \
    requirements.txt > /tmp/requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m pip install --no-cache-dir \
        'langchain>=0.1.0,<1.0' \
        'langchain-openai>=0.1.0,<1.0' \
        'langgraph>=0.1.0,<1.0' \
    && python -m pip install --no-cache-dir 'xgboost-cpu==3.1.2' \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && useradd --create-home --uid 10001 agent

# BBA runtime modules, the full Agent source, saved bindings and manifest.
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent/ ./agent/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml

# Writable HOME and output workspace for the non-root user: the binding and the
# native FileManager write reports under the resolved output_dir.
RUN mkdir -p /home/agent/results \
    && chown -R agent:agent /home/agent

USER agent

FROM continuumio/miniconda3:latest AS dependencies

WORKDIR /opt/agent/agent
RUN ln -s /opt/agent/agent /app

# System packages required by the scientific Python stack
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gfortran \
    git \
    cmake \
    pkg-config \
    curl \
    liblapack-dev \
    libblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Use conda for packages that are typically more reliable from conda-forge
RUN conda install -y -c conda-forge \
    python=3.11 \
    rdkit \
    nwchem \
    && conda clean -afy

# The PyPI CUDA dependency set includes unsupported wheels on Linux ARM.
# Use PyTorch's CPU distribution on ARM; x86 retains its normal PyPI selection.
RUN if [ "$(uname -m)" = "aarch64" ]; then \
    python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch; \
    fi

COPY agent/ /opt/agent/agent

# Resolve ChemGraph, Polar, JupyterLab and TBLite together. Build TBLite from
# source with conservative flags to avoid ABI/symbol issues on ARM.
# pymatgen -> monty pulls an unconstrained ruamel.yaml; conda in the base image
# requires ruamel.yaml<0.19, and `pip check` below fails without this bound.
RUN CFLAGS="-O2 -fno-tree-vectorize" \
    FFLAGS="-O2 -fno-tree-vectorize" \
    python -m pip install --no-cache-dir --no-binary=tblite \
    . jupyterlab -r requirements/mace-polar.txt "tblite==0.4.0" \
    "ruamel.yaml<0.19"

# Use the validated ASE version after all other Python package installs.
RUN python -m pip install --no-cache-dir "ase==3.29.0" && \
    which nwchem && \
    python -c "import ase; from tblite.ase import TBLite; import graph_longrange; print(f'ASE {ase.__version__}')" && \
    python -m pip check

# Allow git commands in bind-mounted repo paths inside the container.
RUN git config --system --add safe.directory /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir 'jsonschema>=4.23,<5' opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
    && useradd --create-home --uid 10001 agent && mkdir /workspace && chown agent:agent /workspace /home/agent
ENV HOME=/home/agent
FROM dependencies
WORKDIR /opt/agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
ENV PYTHONPATH=/opt/abb-runtime
USER agent

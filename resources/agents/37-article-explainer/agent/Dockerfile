FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

WORKDIR /app

COPY . /app

# Install non dev dependencies
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT []
USER nonroot

# Entry port for the streamlit application by default
EXPOSE 8501

# Initial command to run the application
CMD ["/app/.venv/bin/python", "-m", "streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]

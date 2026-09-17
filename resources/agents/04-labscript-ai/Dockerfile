FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/abb-runtime \
    KUMA_DISABLE_UPDATE_CHECK=1 \
    HOME=/tmp \
    LANGCHAIN_TRACING_V2=false \
    LANGSMITH_TRACING=false \
    LANGCHAIN_TRACING=false \
    ANONYMIZED_TELEMETRY=False \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
WORKDIR /opt/agent
COPY agent/ ./agent/
# Upstream's pyproject deps (uv.lock not consistent); pylabrobot simulation in-process. config.py
# hardcodes third-party proxies (ai190/sophnet/siliconflow) AND placeholder api keys, bypassing the
# interceptor and the injected OPENAI_API_KEY; rewrite the base URLs to api.openai.com/v1 and make
# api_key/DEEPSEEK_API_KEY read OPENAI_API_KEY from env so both ChatOpenAI route through the
# interceptor to GLM with the injected credential.
RUN sed -i -e 's#https://api.ai190.com/v1#https://api.openai.com/v1#g' -e 's#https://www.sophnet.com/api/open-apis/v1#https://api.openai.com/v1#g' -e 's#https://api.siliconflow.cn/v1#https://api.openai.com/v1#g' -e 's#api_key = "YOUR_OPENAI_API_KEY"#api_key = __import__("os").environ.get("OPENAI_API_KEY","sk-none")#' -e 's#DEEPSEEK_API_KEY = "YOUR_DEEPSEEK_API_KEY"#DEEPSEEK_API_KEY = __import__("os").environ.get("OPENAI_API_KEY","sk-none")#' agent/backend/config.py \
    && python -m pip install --no-cache-dir ./agent \
    && python -m pip install --no-cache-dir 'opentelemetry-sdk>=1.30,<2' \
    && python -c "import tiktoken; [tiktoken.get_encoding(n) for n in ('cl100k_base', 'o200k_base')]" || true \
    && chmod -R a+rX /opt/tiktoken-cache || true \
    && cd agent && OPENAI_API_KEY=build-check python -c "from backend.pylabrobot_agent import create_pylabrobot_agent; from backend.pylabrobot_utils import load_hardware_configuration" && cd .. \
    && useradd --create-home --uid 10001 agent
COPY .abb-runtime/ /opt/abb-runtime/
COPY bindings/ ./bindings/
COPY agent.toml ./agent.toml
USER agent

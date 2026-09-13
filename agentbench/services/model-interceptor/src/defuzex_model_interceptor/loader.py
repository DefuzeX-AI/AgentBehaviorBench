"""mitmproxy script loader using the mounted service configuration."""

from __future__ import annotations

import os

from defuzex_model_interceptor.addon import ModelInterceptorAddon
from defuzex_model_interceptor.config import ServiceConfig
from defuzex_model_interceptor.entrypoint import CONFIG_ENV, DEFAULT_CONFIG


addons = [
    ModelInterceptorAddon(
        ServiceConfig.load(os.environ.get(CONFIG_ENV, DEFAULT_CONFIG))
    )
]

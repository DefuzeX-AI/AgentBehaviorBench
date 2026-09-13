"""Docker image selection for the standalone model interceptor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbench.runtime.interception import (
    InterceptorImageProvider,
    StaticInterceptorImageProvider,
)

from .image_builder import DockerImageBuilder


INTERCEPTOR_IMAGE_ENV = "DEFUZEX_MODEL_INTERCEPTOR_IMAGE"


@dataclass(frozen=True, slots=True)
class LocalInterceptorImageProvider:
    builder: DockerImageBuilder
    context: Path

    def resolve_image(self) -> str:
        return self.builder.build(
            context=self.context,
            dockerfile=self.context / "Dockerfile",
            repository="model-interceptor",
        )


def default_interceptor_image_provider(
    builder: DockerImageBuilder,
    environ: Mapping[str, str],
) -> InterceptorImageProvider:
    configured = environ.get(INTERCEPTOR_IMAGE_ENV, "").strip()
    if configured:
        return StaticInterceptorImageProvider(configured)
    context = Path(__file__).resolve().parents[2] / "services" / "model-interceptor"
    return LocalInterceptorImageProvider(builder, context)

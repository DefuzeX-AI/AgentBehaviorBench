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
from agentbench.runtime.contracts.execution import Deadline


INTERCEPTOR_IMAGE_ENV = "DEFUZEX_MODEL_INTERCEPTOR_IMAGE"


@dataclass(frozen=True, slots=True)
class LocalInterceptorImageProvider:
    builder: DockerImageBuilder
    context: Path

    def resolve_image(self, *, deadline: Deadline | None = None,
                      log_directory: Path | None = None) -> str:
        return self.builder.build(
            context=self.context,
            dockerfile=self.context / "Dockerfile",
            repository="model-interceptor",
            deadline=deadline,
            log_directory=log_directory,
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

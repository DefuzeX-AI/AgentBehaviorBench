"""Shared source-to-integration command used by CLI and embedded hosts.

The host supplies environment and SDK capabilities, never generation policy.
Certification and runtime execution remain separate, explicit operations.
"""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbench.sdk.contracts import SDKOnboarding
from .source import DownloadedAgent, download_agent
from .resume import download_or_reuse
from .build_agent_env.service import BuildResult, build_agent_environment
from .build_agent_env.build_toml.options import ManifestOptions


@dataclass(frozen=True)
class AddResult:
    source: DownloadedAgent
    configuration: BuildResult | None = None


def add_agent(
    repository: str, agents_directory: Path, *, registry_path: Path,
    build: bool = False, reuse: bool = False, sdk: SDKOnboarding | None = None,
    environ: Mapping[str, str] | None = None, model: str | None = None,
    settings_path: Path | None = None, answers_path: Path | None = None,
    manifest_options: ManifestOptions | None = None,
    on_source: Callable[[DownloadedAgent], None] | None = None, output_fn=print,
) -> AddResult:
    """Preserve plain add, -b resume, and -c source reuse semantics.

    No Agent code is imported or executed here. Paused/unsupported/conflicting
    configuration results are returned intact; the host must not register them.
    """
    if build and (sdk is None or environ is None):
        raise ValueError("Configuration generation requires an explicit SDK and environment")
    source = (download_or_reuse if build or reuse else download_agent)(repository, agents_directory)
    if on_source:
        on_source(source)
    if not build:
        return AddResult(source)
    result = build_agent_environment(
        source, sdk=sdk, registry_path=registry_path, environ=environ,
        settings_path=settings_path, model=model, answers_path=answers_path,
        output_fn=output_fn, manifest_options=manifest_options,
    )
    return AddResult(source, result)

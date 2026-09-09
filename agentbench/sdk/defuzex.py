"""DefuzeX-specific configuration for the compatibility entry points.

Only this integration imports DefuzeX. Generic SDK injection bypasses it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.protocols import SDKRun
from agentbench.harness.registry import AgentRegistration


class DefuzeConfiguration:
    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ

    def prepare(
        self,
        *,
        registration: AgentRegistration,
        requirement_path: str | Path | None,
        case_provider: object | None,
        judge_provider: object | None,
        api_key: str | None,
        max_inputs: int | None,
        allow_local: bool,
        track_files: bool,
        save_local: bool,
    ) -> tuple[str, dict[str, object]]:
        has_case_provider = case_provider is not None
        has_judge_provider = judge_provider is not None
        if has_case_provider != has_judge_provider:
            raise ProviderSelectionError(
                "Provide both case_provider and judge_provider for local mode"
            )

        common: dict[str, object] = {
            "repo_path": registration.path,
            "allow_local": allow_local,
            "track_files": track_files,
            "save_local": save_local,
        }
        if has_case_provider and has_judge_provider:
            if requirement_path is not None:
                common["requirement_path"] = requirement_path
            if max_inputs is None:
                raise ProviderSelectionError(
                    "Local custom Providers require max_inputs"
                )
            common.update(
                case_provider=case_provider,
                judge_provider=judge_provider,
                max_inputs=max_inputs,
            )
            return "local", common

        resolved_key = self._official_api_key(api_key)
        if resolved_key is None:
            raise ProviderSelectionError(
                "No DefuzeX API key or local Provider pair is configured. Set "
                "DEFUZEX_API_KEY or provide both case_provider and "
                "judge_provider."
            )
        resolved_requirement = requirement_path or registration.requirement_path
        if resolved_requirement is None:
            raise ProviderSelectionError(
                "Official DefuzeX Providers require a registered or explicit "
                "requirement_path"
            )
        common["requirement_path"] = resolved_requirement
        common["api_key"] = resolved_key
        return "official", common

    def _official_api_key(self, explicit: str | None) -> str | None:
        """Resolve the API key without logging secrets."""

        return explicit or self._environ.get("DEFUZEX_API_KEY")


def create_run(**kwargs: object) -> SDKRun:
    """Import the SDK lazily so agent-only usage remains lightweight."""

    try:
        from defuzex import create_run
    except ModuleNotFoundError as exc:
        raise ProviderSelectionError(
            "DefuzeX SDK is not installed; install agentbench's [defuzex] extra "
            "or pass sdk=your_sdk"
        ) from exc
    return create_run(**kwargs)  # type: ignore[arg-type, return-value]


def validate_installation(provider_mode: str, run_kwargs: Mapping[str, object]) -> None:
    """Import the SDK and validate official credentials without a request."""

    try:
        from defuzex import DefuzeClient
    except ModuleNotFoundError as exc:
        raise ProviderSelectionError(
            "DefuzeX SDK is not installed; install agentbench's [defuzex] extra "
            "or pass sdk=your_sdk"
        ) from exc

    if provider_mode == "official":
        api_key = run_kwargs.get("api_key")
        DefuzeClient(api_key=api_key if isinstance(api_key, str) else None)


def cli_options(options: Mapping[str, object] | None = None) -> dict[str, object]:
    """Preserve the existing CLI's local-development mode until Worker migration."""
    return {"allow_local": True, "track_files": False, **(options or {})}

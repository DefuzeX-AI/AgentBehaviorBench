"""Load optional host-only environment files for CLI runs."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Mapping
from dataclasses import dataclass
import os
from types import MappingProxyType

from dotenv import load_dotenv

from agentbench.harness.concurrency import ConcurrencySettings


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class EnvironmentFileError(ValueError):
    """Raised when an explicitly selected environment file cannot be loaded."""


def load_project_environment(path: str | Path | None = None) -> Path | None:
    selected = DEFAULT_ENV_FILE if path is None else Path(path).expanduser().resolve()
    if not selected.is_file():
        if path is None:
            return None
        raise EnvironmentFileError(f"Environment file does not exist: {selected}")
    if not load_dotenv(selected, override=False):
        raise EnvironmentFileError(f"Environment file could not be loaded: {selected}")
    return selected


@dataclass(frozen=True, slots=True)
class ExecutionEnvironment:
    environ: Mapping[str, str]
    concurrency: ConcurrencySettings


def execution_environment_snapshot() -> ExecutionEnvironment:
    """Freeze host settings once after the CLI loads its chosen env file."""
    environ = MappingProxyType(dict(os.environ))
    return ExecutionEnvironment(environ, ConcurrencySettings.from_environ(environ))


def load_execution_environment(path: str | Path | None = None) -> ExecutionEnvironment:
    load_project_environment(path)
    return execution_environment_snapshot()

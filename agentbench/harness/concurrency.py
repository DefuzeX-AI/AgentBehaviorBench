"""User-facing Case concurrency settings, independent of any evaluation SDK."""

from collections.abc import Mapping
from dataclasses import dataclass
import re


CASE_CONCURRENCY_ENV = "ABB_MAX_PARALLEL_CASES"


class ConcurrencyConfigurationError(ValueError):
    """Invalid Case worker count supplied by the user."""


@dataclass(frozen=True, slots=True)
class ConcurrencySettings:
    max_parallel_cases: int = 1

    def __post_init__(self) -> None:
        if type(self.max_parallel_cases) is not int or self.max_parallel_cases < 1:
            raise ConcurrencyConfigurationError(
                f"{CASE_CONCURRENCY_ENV} must be a positive integer"
            )

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "ConcurrencySettings":
        # getting the value from environment variable ABB_MAX_PARALLEL_CASES
        value = environ.get(CASE_CONCURRENCY_ENV)
        if value is None:
            return cls()

        
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value.strip()):
            raise ConcurrencyConfigurationError(
                f"{CASE_CONCURRENCY_ENV} must be a positive integer"
            )
        try:
            return cls(int(value.strip()))
        except ValueError as exc:
            raise ConcurrencyConfigurationError(
                f"{CASE_CONCURRENCY_ENV} must be a positive integer"
            ) from exc

    def effective_workers(self, total_case_count: int) -> int:
        if type(total_case_count) is not int or total_case_count < 1:
            raise ValueError("A suite requires at least one selected Case")
        return min(self.max_parallel_cases, total_case_count)

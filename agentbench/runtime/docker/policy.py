"""Security and resource policy applied to every agent container."""

from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

EGRESS_ENV = "ABB_EGRESS"
EGRESS_ALLOW_ENV = "ABB_EGRESS_ALLOW"
DEFAULT_EGRESS_PORTS = (80, 443)

# Package registries an Agent's own tool calls reach when a task needs a missing
# dependency (pip, npm, apt, Maven, cargo, go). Other destinations stay refused.
DEFAULT_EGRESS_ALLOW = (
    "pypi.org", "files.pythonhosted.org",
    "registry.npmjs.org", "registry.yarnpkg.com",
    "deb.debian.org", "security.debian.org",
    "archive.ubuntu.com", "security.ubuntu.com", "ports.ubuntu.com",
    "repo1.maven.org", "repo.maven.apache.org",
    "index.crates.io", "static.crates.io",
    "proxy.golang.org", "sum.golang.org",
)


@dataclass(frozen=True, slots=True)
class EgressSettings:
    """What happens to Agent traffic that is neither a model nor a tool route.

    ``observe`` hands it to the egress observer, which admits the allowlist and
    records every attempt as behavior (issue #137). ``open`` also goes through the
    observer and is recorded the same way, but forwards every destination: for
    evaluating Agents whose real tools (web fetch, git, browsers) reach hosts that
    cannot be listed in advance. ``deny`` keeps the previous in-interceptor refusal.
    Entries are ``host`` or ``*.suffix``, optionally ``:port``; without a port 80 and
    443 are admitted.
    """

    mode: str = "observe"
    allow: tuple[str, ...] = DEFAULT_EGRESS_ALLOW

    def __post_init__(self) -> None:
        if self.mode not in ("observe", "open", "deny"):
            raise ValueError(f"{EGRESS_ENV} must be 'observe', 'open' or 'deny'")
        self.rules()

    @classmethod
    def from_environment(cls, environ: Mapping[str, str],
                         base: "EgressSettings | None" = None) -> "EgressSettings":
        base = base or cls()
        mode = environ.get(EGRESS_ENV, "").strip().lower() or base.mode
        extra = tuple(item for item in environ.get(EGRESS_ALLOW_ENV, "").replace(",", " ").split())
        return cls(mode=mode, allow=base.allow + tuple(item for item in extra if item not in base.allow))

    def rules(self) -> list[dict[str, object]]:
        merged: dict[str, list[int]] = {}
        for entry in self.allow:
            host, sep, port = entry.strip().rpartition(":") if ":" in entry else (entry.strip(), "", "")
            if sep and not (port.isdigit() and 1 <= int(port) <= 65535):
                raise ValueError(f"Invalid {EGRESS_ALLOW_ENV} entry: {entry!r}")
            bare = host[2:] if host.startswith("*.") else host
            if not bare or "*" in bare or any(c in bare for c in "/?[] "):
                raise ValueError(f"Invalid {EGRESS_ALLOW_ENV} entry: {entry!r}")
            ports = merged.setdefault(host.lower().rstrip("."), [])
            for value in ((int(port),) if sep else DEFAULT_EGRESS_PORTS):
                if value not in ports:
                    ports.append(value)
        return [{"host": host, "ports": ports} for host, ports in merged.items()]

    @property
    def uses_observer(self) -> bool:
        return self.mode in ("observe", "open")


MEMORY_ENV = "ABB_DOCKER_MEMORY"
CPUS_ENV = "ABB_DOCKER_CPUS"

# Positive integer followed by unit [k, m, g, K, M, G]
_MEMORY_REGEX = re.compile(r"^[1-9][0-9]*[kmgKMG]$")

# Minimum and maximum CPU bounds for Docker container
MIN_CPUS = 0.0
MAX_CPUS = 1024.0


def _validate_docker_memory(memory: str) -> str:
    """Validate Docker container memory limit format.

    Constraints:
        Must be a non-empty string consisting of a positive integer followed by
        a standard memory unit suffix [k, m, g, K, M, G] (e.g. '8g', '512m', '2G').
        Values such as '0g', '-8g', floats ('8.5g'), non-numeric characters, or
        missing units ('8') are invalid and raise ValueError.

    Args:
        memory: The memory string to validate.

    Returns:
        The validated and stripped memory string.

    Raises:
        ValueError: If memory does not match the required format.
    """
    if not isinstance(memory, str):
        raise ValueError(f"Memory limit must be a string, got {type(memory).__name__}")
    stripped = memory.strip()
    if not _MEMORY_REGEX.fullmatch(stripped):
        raise ValueError(
            f"Invalid memory limit format: {memory!r}. "
            f"Must match positive integer with unit [kmgKMG] (e.g. '8g', '512m', '2G')."
        )
    return stripped


def _validate_docker_cpus(cpus: float | int | str) -> float | int:
    """Validate Docker container CPU allocation limit.

    Constraints:
        Must be a positive numeric value strictly greater than 0.0 and less than or
        equal to 1024.0. Non-numeric strings, negative numbers, zero, NaN, infinities,
        and boolean values are invalid and raise ValueError.

    Args:
        cpus: The CPU limit to validate (numeric value or numeric string).

    Returns:
        The validated CPU value. When passed as an integer (and not a string),
        the integer value is returned to preserve argument formatting in downstream consumers.

    Raises:
        ValueError: If cpus cannot be parsed as a positive float within (0.0, 1024.0].
    """
    if isinstance(cpus, bool):
        raise ValueError(f"Invalid cpus value {cpus!r}: boolean is not allowed.")
    try:
        val = float(cpus)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid cpus format: {cpus!r}. Must parse as a positive float.")
    if math.isnan(val) or math.isinf(val) or val <= MIN_CPUS or val > MAX_CPUS:
        raise ValueError(
            f"Invalid cpus value: {val}. Must be a positive float within 0.0 < float(cpus) <= 1024.0."
        )
    if isinstance(cpus, int) and not isinstance(cpus, str):
        return cpus
    return val


@dataclass(frozen=True, slots=True)
class DockerPolicy:
    """Security and resource limits applied to every agent container.

    Attributes:
        cpus: Maximum CPU quota allocated to the container (--cpus). Must satisfy
            0.0 < float(cpus) <= 1024.0. Defaults to 1.0; dynamically overridden
            via the ``ABB_DOCKER_CPUS`` environment variable when default (1.0).
            For CPU-intensive neural models (e.g. Marker/Surya layout and OCR predictors),
            configure via ABB_DOCKER_CPUS (e.g. 4.0).
        memory: Maximum memory limit for the container (--memory). Must match
            a positive integer followed by a unit suffix [kmgKMG] (e.g. '8g', '512m', '2G').
            Defaults to '1g'; dynamically overridden via the ``ABB_DOCKER_MEMORY``
            environment variable when default ('1g'). For heavy vision and multimodal agents,
            configure via ABB_DOCKER_MEMORY (e.g. '8g') to prevent kernel OOM cgroup termination (exit code 137).
        pids_limit: Maximum number of simultaneous processes (--pids-limit).
        tmpfs_size: Capacity limit for in-memory tmpfs mounts (/tmp, /run/agentbench-tools).
        egress: Network egress filtering policy.
    """

    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    # Capacity limit, not a reservation; tmpfs usage also counts toward memory.
    tmpfs_size: str = "1g"
    egress: EgressSettings = EgressSettings()

    def __post_init__(self) -> None:
        mem = self.memory
        if self.memory == "1g" and MEMORY_ENV in os.environ:
            mem = os.environ[MEMORY_ENV]
        validated_mem = _validate_docker_memory(mem)
        object.__setattr__(self, "memory", validated_mem)

        c = self.cpus
        if self.cpus == 1.0 and CPUS_ENV in os.environ:
            raw_cpus = os.environ[CPUS_ENV].strip()
            parsed_c = _validate_docker_cpus(raw_cpus)
            c = float(parsed_c) if not isinstance(parsed_c, float) else parsed_c
        else:
            c = _validate_docker_cpus(c)
        object.__setattr__(self, "cpus", c)

    def run_arguments(self) -> tuple[str, ...]:
        return (
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            f"--tmpfs=/tmp:rw,exec,nosuid,nodev,size={self.tmpfs_size},mode=1777",
            f"--tmpfs=/run/agentbench-tools:rw,exec,nosuid,nodev,size={self.tmpfs_size},mode=1777",
        )

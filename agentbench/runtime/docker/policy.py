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

# Positive integer followed by a unit [k, m, g, K, M, G].
_MEMORY_REGEX = re.compile(r"^[1-9][0-9]*[kmgKMG]$")

MIN_CPUS = 0.0
MAX_CPUS = 1024.0


def _validate_docker_memory(memory: str) -> str:
    """Validate a Docker ``--memory`` limit such as ``8g`` or ``512m``.

    ``0g``, negative or fractional values, a missing unit and non-string values
    are rejected before Docker receives the argument.
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
    """Validate a Docker ``--cpus`` quota within ``0.0 < float(cpus) <= 1024.0``.

    Booleans, NaN, infinities and out-of-range values are rejected. Integers are
    returned unchanged so ``--cpus=2`` is not rendered as ``--cpus=2.0``.
    """
    if isinstance(cpus, bool):
        raise ValueError(f"Invalid cpus value {cpus!r}: boolean is not allowed.")
    try:
        value = float(cpus)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid cpus format: {cpus!r}. Must parse as a positive float.")
    if math.isnan(value) or math.isinf(value) or value <= MIN_CPUS or value > MAX_CPUS:
        raise ValueError(
            f"Invalid cpus value: {value}. Must be a positive float within 0.0 < float(cpus) <= 1024.0."
        )
    if isinstance(cpus, int) and not isinstance(cpus, str):
        return cpus
    return value


@dataclass(frozen=True, slots=True)
class DockerPolicy:
    """Security and resource limits applied to every agent container.

    Constructor arguments are always honored. :meth:`from_environment`
    optionally resolves ``ABB_DOCKER_MEMORY`` and ``ABB_DOCKER_CPUS`` from an
    explicit environment mapping for CPU- or memory-intensive Agents such as
    Marker/Surya OCR pipelines, which otherwise hit the 1 GiB default.
    """

    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    # Capacity limit, not a reservation; tmpfs usage also counts toward memory.
    tmpfs_size: str = "1g"
    egress: EgressSettings = EgressSettings()

    def __post_init__(self) -> None:
        object.__setattr__(self, "memory", _validate_docker_memory(self.memory))
        object.__setattr__(self, "cpus", _validate_docker_cpus(self.cpus))

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
        base: DockerPolicy | None = None,
    ) -> DockerPolicy:
        """Build a policy from an explicit environment mapping or ambient ``os.environ``.

        An explicit empty mapping uses defaults without ambient bleed. ``base``
        supplies values for settings the environment does not override.
        """
        env = os.environ if environ is None else environ
        base_policy = base or cls()

        memory = env.get(MEMORY_ENV, base_policy.memory)
        raw_cpus = env.get(CPUS_ENV)
        cpus = base_policy.cpus if raw_cpus is None else _validate_docker_cpus(raw_cpus.strip())

        return cls(
            cpus=cpus,
            memory=memory,
            pids_limit=base_policy.pids_limit,
            tmpfs_size=base_policy.tmpfs_size,
            egress=EgressSettings.from_environment(env, base=base_policy.egress),
        )

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

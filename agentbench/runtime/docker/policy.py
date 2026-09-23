"""Security and resource policy applied to every agent container."""

from __future__ import annotations

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
    records every attempt as behavior (issue #137). ``deny`` keeps the previous
    in-interceptor refusal. Entries are ``host`` or ``*.suffix``, optionally
    ``:port``; without a port 80 and 443 are admitted.
    """

    mode: str = "observe"
    allow: tuple[str, ...] = DEFAULT_EGRESS_ALLOW

    def __post_init__(self) -> None:
        if self.mode not in ("observe", "deny"):
            raise ValueError(f"{EGRESS_ENV} must be 'observe' or 'deny'")
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


@dataclass(frozen=True, slots=True)
class DockerPolicy:
    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    # Capacity limit, not a reservation; tmpfs usage also counts toward memory.
    tmpfs_size: str = "1g"
    egress: EgressSettings = EgressSettings()

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

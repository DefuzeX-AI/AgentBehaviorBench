"""Host allowlist for non-model egress. Everything not listed is denied and recorded."""

from __future__ import annotations

from dataclasses import dataclass


def normalize_host(host: str) -> str:
    return host.strip().rstrip(".").lower()


@dataclass(frozen=True, slots=True)
class AllowRule:
    """An exact host, or ``*.suffix`` for strict subdomains of ``suffix``."""

    host: str
    ports: tuple[int, ...]

    def __post_init__(self) -> None:
        host = self.host
        if not isinstance(host, str) or not normalize_host(host):
            raise ValueError("Allow rule host must be a non-empty string")
        bare = host[2:] if host.startswith("*.") else host
        if "*" in bare or any(c in bare for c in "/?[]: ") or not bare:
            raise ValueError(f"Unsafe allow rule host: {host!r}")
        object.__setattr__(self, "host", normalize_host(host))

    def matches(self, host: str, port: int) -> bool:
        if port not in self.ports:
            return False
        host = normalize_host(host)
        if self.host.startswith("*."):
            return host.endswith(self.host[1:]) and host != self.host[2:]
        return host == self.host


@dataclass(frozen=True, slots=True)
class AllowList:
    rules: tuple[AllowRule, ...] = ()

    def match(self, host: str, port: int) -> AllowRule | None:
        return next((rule for rule in self.rules if rule.matches(host, port)), None)

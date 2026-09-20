"""Restricted Docker policy for the trusted network interceptor."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass


DOCKER_DNS_ENV = "ABB_DOCKER_DNS"


@dataclass(frozen=True, slots=True)
class InterceptorPolicy:
    memory: str = "512m"
    cpus: float = 1.0
    pids_limit: int = 128
    dns_servers: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> "InterceptorPolicy":
        raw = environ.get(DOCKER_DNS_ENV, "")
        servers: list[str] = []
        for item in raw.replace(",", " ").split():
            try:
                server = str(ipaddress.ip_address(item))
            except ValueError as exc:
                raise ValueError(
                    f"{DOCKER_DNS_ENV} must contain only comma- or space-separated IP addresses"
                ) from exc
            if server not in servers:
                servers.append(server)
        return cls(dns_servers=tuple(servers))

    def run_arguments(self) -> tuple[str, ...]:
        arguments = (
            "--read-only",
            "--cap-drop=ALL",
            "--cap-add=NET_ADMIN",
            "--cap-add=NET_RAW",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs=/run/defuzex:rw,noexec,nosuid,size=64m",
        )
        dns_arguments = (
            argument
            for server in self.dns_servers
            for argument in ("--dns", server)
        )
        return (*arguments, *dns_arguments)

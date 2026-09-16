"""Security and resource policy applied to every agent container."""

from __future__ import annotations

from dataclasses import dataclass, field
import os


def host_user() -> str | None:
    """Return ``uid:gid`` for running Agent containers as the invoking host user.

    The host and the container exchange every evaluation file through bind mounts:
    settings go in, and artifacts, saved Cases and the SDK request ledger come back.
    Under the image's own non-root user the two sides are different uids, so on a
    native Linux Docker Engine (no uid remapping, unlike Docker Desktop) a file
    either side writes owner-only is unreadable to the other. The SDK writes its
    request ledger 0600 by design, so no mode change can fix that direction.

    Matching the uid removes the whole class. The image must still declare a
    non-root USER; this only selects which unprivileged uid runs it. A root host
    has nothing to match, and platforms without POSIX uids keep the image user.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None or getuid() == 0:
        return None
    return f"{getuid()}:{getgid()}"


@dataclass(frozen=True, slots=True)
class DockerPolicy:
    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    tmpfs_size: str = "64m"
    user: str | None = field(default_factory=host_user)

    def run_arguments(self) -> tuple[str, ...]:
        return (
            *((f"--user={self.user}",) if self.user else ()),
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            f"--tmpfs=/tmp:rw,noexec,nosuid,size={self.tmpfs_size}",
            f"--tmpfs=/run/agentbench-tools:rw,exec,nosuid,nodev,size={self.tmpfs_size},mode=1777",
        )

"""Security and resource policy applied to every agent container."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DockerPolicy:
    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    # Capacity limit, not a reservation; tmpfs usage also counts toward memory.
    tmpfs_size: str = "1g"

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

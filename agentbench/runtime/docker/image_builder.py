"""Content-addressed Docker image builds for agents and trusted services."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from agentbench.runtime.contracts.execution import Deadline, RunCancelled, RunControl, RuntimeInfrastructureError
from .build_coordinator import BuildCoordinator
from .command import DockerCommandRunner, DockerCommandTimeout


class DockerBuildError(RuntimeError):
    """Raised when Docker cannot inspect or build a required image."""


IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}


@dataclass(frozen=True, slots=True)
class DockerImageBuilder:
    executable: str = "docker"
    coordinator: BuildCoordinator = field(default_factory=BuildCoordinator)
    control: RunControl | None = None
    command_runner: DockerCommandRunner | None = None
    build_timeout: float = 1800
    environ: Mapping[str, str] | None = None

    def build(
        self,
        *,
        context: Path,
        dockerfile: Path,
        repository: str,
        fingerprint_paths: Sequence[Path] | None = None,
        control: RunControl | None = None,
        deadline: Deadline | None = None,
        log_directory: Path | None = None,
    ) -> str:
        control = control or self.control
        deadline = deadline or Deadline.after(self.build_timeout)
        context = context.resolve()
        dockerfile = dockerfile.resolve()
        selected = None if fingerprint_paths is None else (*fingerprint_paths, dockerfile)
        content_digest = _content_digest(context, fingerprint_paths=selected,
                                         control=control, deadline=deadline)
        # Selecting another Dockerfile from the same context changes the build.
        digest = hashlib.sha256((content_digest + "\0" + str(dockerfile.relative_to(context))).encode()).hexdigest()
        tag = f"defuzex-agentbench/{_safe_name(repository)}:{digest}"
        commands = self.command_runner or DockerCommandRunner(self.executable, environ=self.environ)

        def inspect_cached() -> str | None:
            inspected = commands.run(
                ["image", "inspect", "--format", '{{index .Config.Labels "abb.build_fingerprint"}}', tag],
                control=control, deadline=deadline,
            )
            if inspected.returncode != 0:
                return None
            if inspected.stdout.strip() != digest:
                raise DockerBuildError(f"Docker image fingerprint does not match: {tag}")
            return tag

        def build_once() -> str:
            try:
                built = commands.run(
                    ["build", "--tag", tag, "--label", f"abb.build_fingerprint={digest}",
                     "--file", str(dockerfile), str(context)],
                    control=control, deadline=deadline, timeout=self.build_timeout,
                    log_directory=log_directory,
                )
            except (RunCancelled, DockerCommandTimeout) as exc:
                raise RuntimeInfrastructureError(
                    f"Docker build client interrupted for {tag}; daemon build state is unknown"
                ) from exc
            if built.returncode != 0:
                detail = (built.stderr or built.stdout).strip()
                raise DockerBuildError(f"Docker image build failed: {detail}")
            return tag

        return self.coordinator.resolve(
            (self.executable, tag), inspect_cached=inspect_cached, build_once=build_once,
            control=control, deadline=deadline,
        )


def _content_digest(
    root: Path, *, fingerprint_paths: Sequence[Path] | None = None,
    control: RunControl | None = None, deadline: Deadline | None = None,
) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    candidates: set[Path] = set()
    for selected in fingerprint_paths or (root,):
        selected = selected.resolve()
        if not selected.is_relative_to(root.resolve()):
            raise DockerBuildError(f"Fingerprint path escapes build context: {selected}")
        if selected.is_file():
            candidates.add(selected)
        elif selected.is_dir():
            for path in selected.rglob("*"):
                _check(control, deadline)
                if path.is_file():
                    candidates.add(path)

    files = sorted(
        path
        for path in candidates
        if path.is_file()
        and not any(part in IGNORED_PARTS or part.endswith(".egg-info") for part in path.parts)
        and path.name != ".env"
    )
    for path in files:
        _check(control, deadline)
        if not path.resolve().is_relative_to(root):
            raise DockerBuildError(f"Fingerprint path escapes build context: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(path.stat().st_size.to_bytes(8, "big"))
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                _check(control, deadline)
                digest.update(block)
    return digest.hexdigest()


def _check(control: RunControl | None, deadline: Deadline | None) -> None:
    if control is not None:
        control.check()
    if deadline is not None:
        deadline.check()


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    return normalized or "agent"

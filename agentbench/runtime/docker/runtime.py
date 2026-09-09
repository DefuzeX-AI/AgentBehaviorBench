"""Local Docker runtime with transparent model traffic interception."""

from __future__ import annotations

import json
import math
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import uuid4

from agentbench.adapter import AgentDescriptor
from agentbench.runtime.agentcontainer import AgentContainerConfig
from agentbench.runtime.contracts import (
    EnvironmentSecretResolver,
    RuntimeSession,
    SecretResolver,
)
from agentbench.runtime.interception import (
    DEFAULT_TRACE_MAX_BYTES,
    InterceptionConfig,
    InterceptionTraceState,
    InterceptorImageProvider,
    ModelTargetProvider,
    NullTraceSink,
    OpenRouterProvider,
    RunningModelInterceptor,
    TraceEvent,
    TraceSink,
    get_trust_plugin,
)

from .image_builder import DockerImageBuilder
from .interceptor_image import default_interceptor_image_provider
from .interceptor_policy import InterceptorPolicy
from .policy import DockerPolicy
from .session import DockerSession
from .worker_build import worker_build_context


class DockerRuntimeError(RuntimeError):
    """Raised when an isolated Docker session cannot be started."""


class DockerRuntime:
    def __init__(
        self,
        *,
        executable: str = "docker",
        environ: Mapping[str, str] | None = None,
        secret_resolver: SecretResolver | None = None,
        policy: DockerPolicy | None = None,
        interceptor_policy: InterceptorPolicy | None = None,
        interceptor_image_provider: InterceptorImageProvider | None = None,
        model_provider: ModelTargetProvider | None = None,
        trace_sink: TraceSink | None = None,
        trace_max_bytes: int = DEFAULT_TRACE_MAX_BYTES,
        artifact_root: Path | None = None,
        timeout_sec: float | None = None,
        run_id: str | None = None,
    ) -> None:
        if trace_max_bytes < 1024:
            raise ValueError("trace_max_bytes must be at least 1024")
        if timeout_sec is not None and (isinstance(timeout_sec, bool) or not math.isfinite(timeout_sec) or timeout_sec <= 0):
            raise ValueError("timeout_sec must be finite and positive")
        self._executable = executable
        self._environ = os.environ if environ is None else environ
        self._secret_resolver = secret_resolver or EnvironmentSecretResolver(
            self._environ
        )
        self._policy = policy or DockerPolicy()
        self._interceptor_policy = interceptor_policy or InterceptorPolicy()
        self._images = DockerImageBuilder(executable)
        self._interceptor_images = (
            interceptor_image_provider
            or default_interceptor_image_provider(self._images, self._environ)
        )
        self._model_provider = model_provider or OpenRouterProvider()
        self._trace_sink = trace_sink or NullTraceSink()
        self._trace_max_bytes = trace_max_bytes
        self.artifact_root = artifact_root
        self._timeout_override = timeout_sec
        self.run_id = run_id

    def invocation_timeout(self, agent):
        return self._timeout_override or AgentContainerConfig.from_agent_dir(
            agent.path, secret_resolver=self._secret_resolver, environ=self._environ).timeout_sec

    def start(self, agent: AgentDescriptor, *, invocation=None) -> RuntimeSession:
        self._check_available()
        config = AgentContainerConfig.from_agent_dir(
            agent.path,
            secret_resolver=self._secret_resolver,
            environ=self._environ,
        )
        interception = InterceptionConfig.from_agent_dir(agent.path)
        if interception is not None:
            target = self._model_provider.resolve(self._environ)
            self._secret_resolver.require(target.credential_env)
        if invocation is not None:
            with worker_build_context(config) as (context, dockerfile):
                image = self._images.build(context=context, dockerfile=dockerfile, repository=config.agent_id)
            self._require_non_root_image(image)
        else:
            image = self._images.build(
                context=config.build_context,
                dockerfile=config.dockerfile,
                repository=config.agent_id,
            )

        suffix = uuid4().hex[:12]
        network_name = f"defuzex-{suffix}-egress"
        agent_name = f"defuzex-{suffix}-agent"
        interceptor: RunningModelInterceptor | None = None
        trace_state: InterceptionTraceState | None = None
        created_network = False

        try:
            agent_environment = dict(config.environment)
            network_arguments: list[str]
            if interception is not None:
                trace_state = InterceptionTraceState()
                self._require_non_root_image(image)
                self._run("network", "create", network_name)
                created_network = True
                interceptor, token_environment = self._start_interceptor(
                    agent_id=config.agent_id,
                    interception=interception,
                    suffix=suffix,
                    network_name=network_name,
                    trace_state=trace_state,
                )
                agent_environment.update(interception.environment)
                agent_environment.update(token_environment)
                certificate_target = "/run/defuzex-ca/ca.pem"
                agent_environment.update(
                    get_trust_plugin(interception.trust_plugin).agent_environment(
                        certificate_target
                    )
                )
                network_arguments = [
                    "--network",
                    f"container:{interceptor.container_name}",
                ]
            else:
                self._run("network", "create", "--internal", network_name)
                created_network = True
                network_arguments = ["--network", network_name]

            command = [
                self._executable,
                "run",
                "--rm",
                "--init",
                "--name",
                agent_name,
                *network_arguments,
                "--workdir",
                config.workdir,
                *self._policy.run_arguments(),
            ]
            if interceptor is not None:
                command.extend(
                    (
                        "--mount",
                        _bind_mount(
                            interceptor.ca_certificate,
                            "/run/defuzex-ca/ca.pem",
                        ),
                    )
                )
            if invocation is not None:
                inputs, outputs = invocation
                command.extend(("--mount", _bind_mount(inputs, "/run/abb-input")))
                # All other filesystem locations retain the existing read-only policy.
                command.extend(("--mount", f"type=bind,source={outputs},target=/run/abb-output"))
            agent_environment.update(
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONUNBUFFERED="1",
            )
            for key, value in sorted(agent_environment.items()):
                command.extend(("--env", f"{key}={value}"))
            command.extend((image, *config.argv))

            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            cleaned = False

            def cleanup() -> None:
                nonlocal cleaned
                if cleaned:
                    return
                cleaned = True
                self._run_quiet("container", "rm", "--force", agent_name)
                if interceptor is not None:
                    interceptor.close()
                if created_network:
                    self._run_quiet("network", "rm", network_name)

            return DockerSession(
                process,
                close_callback=cleanup,
                trace_checkpoint=(
                    trace_state.checkpoint
                    if interception is not None and interception.required
                    else None
                ),
                trace_validator=(
                    self._required_trace_callback(trace_state)
                    if interception is not None and interception.required
                    else None
                ),
            )
        except BaseException:
            self._run_quiet("container", "rm", "--force", agent_name)
            if interceptor is not None:
                interceptor.close()
            if created_network:
                self._run_quiet("network", "rm", network_name)
            raise

    def _start_interceptor(
        self,
        *,
        agent_id: str,
        interception: InterceptionConfig,
        suffix: str,
        network_name: str,
        trace_state: InterceptionTraceState,
    ) -> tuple[RunningModelInterceptor, dict[str, str]]:
        image = self._interceptor_images.resolve_image()
        container_name = f"defuzex-{suffix}-interceptor"
        secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
        config_file = secret_dir / "interceptor_config.json"
        ca_dir = secret_dir / "ca"
        ca_dir.mkdir()
        ca_certificate = ca_dir / "mitmproxy-ca-cert.pem"
        token_environment: dict[str, str] = {}
        credentials: list[dict[str, object]] = []
        target = self._model_provider.resolve(self._environ)
        upstream_secret = self._secret_resolver.require(target.credential_env)
        target_secret_file = secret_dir / "target.secret"
        target_secret_file.write_text(upstream_secret, encoding="utf-8")

        for credential in interception.credentials:
            token = secrets.token_urlsafe(32)
            token_file = secret_dir / f"{credential.credential_id}.token"
            token_file.write_text(token, encoding="utf-8")
            token_environment[credential.agent_env] = token
            credentials.append(
                {
                    "id": credential.credential_id,
                    "auth_plugin": credential.auth_plugin,
                    "token_file": f"/run/secrets/{token_file.name}",
                    "secret_file": "/run/secrets/target.secret",
                }
            )

        config_file.write_text(
            json.dumps(
                {
                    "agent_id": agent_id,
                    "max_trace_bytes": self._trace_max_bytes,
                    "target": {
                        "provider_id": target.provider_id,
                        "target_plugin": target.target_plugin,
                        "base_url": target.base_url,
                        "model": target.model,
                        "headers": dict(target.headers),
                    },
                    "credentials": credentials,
                    "routes": [
                        {
                            "id": route.route_id,
                            "host_patterns": list(route.host_patterns),
                            "ports": list(route.ports),
                            "methods": list(route.methods),
                            "path_patterns": list(route.path_patterns),
                            "protocol_plugin": route.protocol_plugin,
                            "credential": route.credential_id,
                        }
                        for route in interception.routes
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        try:
            command = [
                "run",
                "--detach",
                "--init",
                "--name",
                container_name,
                "--network",
                network_name,
                *self._interceptor_policy.run_arguments(),
                "--mount",
                _bind_mount(config_file, "/run/secrets/interceptor_config"),
                "--mount",
                _writable_bind_mount(ca_dir, "/run/defuzex/ca"),
            ]
            for path in sorted(secret_dir.glob("*.token")) + sorted(
                secret_dir.glob("*.secret")
            ):
                command.extend(
                    ("--mount", _bind_mount(path, f"/run/secrets/{path.name}"))
                )
            command.append(image)
            self._run(*command)
            self._wait_for_interceptor(container_name, ca_certificate)
            if not ca_certificate.is_file():
                raise DockerRuntimeError("Model interceptor CA was not exported")
            log_process = self._follow_trace(container_name, trace_state)
        except BaseException:
            self._run_quiet("container", "rm", "--force", container_name)
            shutil.rmtree(secret_dir, ignore_errors=True)
            raise

        def close_interceptor() -> None:
            self._run_quiet("container", "rm", "--force", container_name)
            shutil.rmtree(secret_dir, ignore_errors=True)

        return (
            RunningModelInterceptor(
                container_name=container_name,
                ca_certificate=ca_certificate,
                _close_callback=close_interceptor,
                _log_process=log_process,
            ),
            token_environment,
        )

    def _follow_trace(
        self, container_name: str, trace_state: InterceptionTraceState
    ) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            [self._executable, "logs", "--follow", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if process.stdout is None:  # pragma: no cover - subprocess contract
            raise DockerRuntimeError("Docker trace stream was not created")

        def consume() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                event = TraceEvent.from_log_line(line.rstrip("\r\n"))
                if event is not None:
                    try:
                        # A pair is complete only after its full event is saved.
                        self._trace_sink.emit(event)
                    except Exception:
                        trace_state.fail()
                        return
                    trace_state.emit(event)

        threading.Thread(
            target=consume,
            daemon=True,
            name=f"{container_name}-trace",
        ).start()
        return process

    @staticmethod
    def _required_trace_callback(
        trace_state: InterceptionTraceState,
    ) -> Callable[[object], None]:
        def require_trace(value: object) -> None:
            checkpoint = int(value)
            if not trace_state.wait_for_completion_after(checkpoint, timeout=2):
                raise DockerRuntimeError(
                    "Agent invocation completed without a matched LLM request/response trace"
                )
            if not trace_state.wait_for_idle():
                raise DockerRuntimeError("Model trace is incomplete: unfinished pair, capture error, truncation, or failed persistence")

        return require_trace

    def _wait_for_interceptor(
        self, container_name: str, ca_certificate: Path
    ) -> None:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            logs = self._run_quiet("logs", container_name, capture=True)
            if (
                logs is not None
                and '"event": "interceptor_ready"' in logs.stdout
                and ca_certificate.is_file()
                and ca_certificate.stat().st_size > 0
            ):
                return
            state = self._run_quiet(
                "inspect",
                "--format",
                "{{.State.Running}}",
                container_name,
                capture=True,
            )
            if state is not None and state.stdout.strip() == "false":
                detail = logs.stdout.strip() if logs is not None else ""
                raise DockerRuntimeError(
                    f"Model interceptor stopped during startup{': ' + detail if detail else ''}"
                )
            time.sleep(0.25)
        logs = self._run_quiet("logs", container_name, capture=True)
        detail = logs.stdout.strip() if logs is not None else ""
        raise DockerRuntimeError(
            f"Model interceptor did not become ready{': ' + detail if detail else ''}"
        )

    def _require_non_root_image(self, image: str) -> None:
        result = self._run(
            "image", "inspect", "--format", "{{.Config.User}}", image
        )
        user = result.stdout.strip()
        if not user or user in {"0", "root", "0:0", "root:root"}:
            raise DockerRuntimeError(
                "Transparent interception requires an Agent image with a non-root USER"
            )

    def _check_available(self) -> None:
        result = self._run_quiet("info", "--format", "{{.ServerVersion}}", capture=True)
        if result is None or result.returncode != 0:
            detail = result.stderr.strip() if result is not None else "docker not found"
            raise DockerRuntimeError(f"Docker daemon is unavailable: {detail}")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = self._run_quiet(*args, capture=True)
        if result is None:
            raise DockerRuntimeError("Docker executable was not found")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise DockerRuntimeError(f"Docker command failed: {detail}")
        return result

    def _run_quiet(
        self, *args: str, capture: bool = False
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                [self._executable, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError:
            return None


def _bind_mount(source: Path, target: str) -> str:
    return f"type=bind,source={source.resolve()},target={target},readonly"


def _writable_bind_mount(source: Path, target: str) -> str:
    return f"type=bind,source={source.resolve()},target={target}"

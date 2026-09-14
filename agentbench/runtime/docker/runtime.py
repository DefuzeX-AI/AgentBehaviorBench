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
from agentbench.runtime.contracts.execution import (
    Deadline, DockerCleanupError, RunControl, RuntimeInfrastructureError, RuntimeLimits,
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
from .build_coordinator import BuildCoordinator
from .command import DockerCommandRunner, DockerCommandTimeout
from .interceptor_image import LocalInterceptorImageProvider, default_interceptor_image_provider
from .interceptor_policy import InterceptorPolicy
from .policy import DockerPolicy
from .session import DockerSession
from .resources import ResourceRegistry
from .worker_build import worker_build_context


class DockerRuntimeError(RuntimeError):
    """Raised when an isolated Docker session cannot be started."""


class DockerUnavailableError(DockerRuntimeError, RuntimeInfrastructureError):
    """A shared Docker daemon failure must stop further Suite dispatch."""


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
        control: RunControl | None = None,
        build_coordinator: BuildCoordinator | None = None,
        identity: Mapping[str, object] | None = None,
        resource_registry: ResourceRegistry | None = None,
        limits: RuntimeLimits | None = None,
        command_environ: Mapping[str, str] | None = None,
    ) -> None:
        if trace_max_bytes < 1024:
            raise ValueError("trace_max_bytes must be at least 1024")
        if timeout_sec is not None and (isinstance(timeout_sec, bool) or not math.isfinite(timeout_sec) or timeout_sec <= 0):
            raise ValueError("timeout_sec must be finite and positive")
        self._executable = executable
        self._environ = dict(os.environ if environ is None else environ)
        self.control = control or RunControl()
        self.identity = dict(identity or {})
        self._limits = limits or RuntimeLimits()
        self._resources = resource_registry or ResourceRegistry()
        self._uncertain_resources: set[tuple[str, str]] = set()
        client_environment = dict(os.environ if command_environ is None else command_environ)
        client_environment.update(self._environ)
        self._commands = DockerCommandRunner(executable, environ=client_environment)
        self._secret_resolver = secret_resolver or EnvironmentSecretResolver(
            self._environ
        )
        self._policy = policy or DockerPolicy()
        self._interceptor_policy = interceptor_policy or InterceptorPolicy()
        self._images = DockerImageBuilder(
            executable, coordinator=build_coordinator or BuildCoordinator(),
            control=self.control, command_runner=self._commands,
            build_timeout=self._limits.build_seconds,
        )
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

    def start(self, agent: AgentDescriptor, *, invocation=None,
              preparation_deadline: Deadline | None = None) -> RuntimeSession:
        # 先检查是否取消、准备是否超时，以及 Docker 是否可用
        self.control.check()
        preparation = preparation_deadline or Deadline.after(self._limits.preparation_seconds)
        preparation.check()
        self._check_available(deadline=preparation)
        # 读取 Agent 的容器配置和网络拦截配置
        config = AgentContainerConfig.from_agent_dir(
            agent.path,
            secret_resolver=self._secret_resolver,
            environ=self._environ,
        )
        interception = InterceptionConfig.from_agent_dir(agent.path)
        if interception is not None:
            # 配置了网络拦截时，先确认模型服务和所需密钥
            target = self._model_provider.resolve(self._environ)
            self._secret_resolver.require(target.credential_env)
        if invocation is not None:
            # 有输入输出目录的任务：准备 worker 构建上下文，再构建镜像
            with worker_build_context(config, control=self.control, deadline=preparation) as (context, dockerfile):
                image = self._images.build(context=context, dockerfile=dockerfile, repository=config.agent_id,
                                           deadline=preparation, log_directory=self._build_logs())
            self._require_non_root_image(image, deadline=preparation)
        else:
            # 普通启动：使用 Agent 自己的构建目录和 Dockerfile
            image = self._images.build(
                context=config.build_context,
                dockerfile=config.dockerfile,
                repository=config.agent_id,
                deadline=preparation,
                log_directory=self._build_logs(),
            )

        self.control.check()


        # 给本次容器和网络取独立名字，避免并发任务冲突。
        suffix = uuid4().hex
        network_name = f"defuzex-{suffix}-egress"
        agent_name = f"defuzex-{suffix}-agent"
        interceptor: RunningModelInterceptor | None = None
        trace_state: InterceptionTraceState | None = None
        planned_network = False
        planned_agent = False
        process: subprocess.Popen[str] | None = None
        session: DockerSession | None = None
        cleanup_lock = threading.Lock()
        cleaned = False
        cleanup_error: DockerCleanupError | None = None

        def cleanup() -> None:
            # 定义退出时的清理动作；这里只定义，尚未执行
            nonlocal cleaned, cleanup_error
            with cleanup_lock:
                # 防止多个退出路径重复清理同一批资源
                if cleaned:
                    if cleanup_error is not None:
                        raise cleanup_error
                    return
                cleaned = True
                deadline = Deadline.after(self._limits.cleanup_seconds)
                errors: list[str] = []

                if planned_agent:
                    # 先尝试正常停止 Agent，再移除容器
                    if process is not None and process.poll() is None and not self.control.forced:
                        try:
                            self._commands.run(["container", "stop", "--time", "5", agent_name],
                                               cleanup=True, timeout=7, deadline=deadline)
                        except Exception:
                            pass  # Force removal below is authoritative.
                    try:
                        self._remove_resource("container", agent_name, deadline=deadline)
                    except Exception as exc:
                        errors.append(str(exc))

                if self.control.cancelled and trace_state is not None:
                    trace_state.fail()

                if interceptor is not None:
                    # Agent 停止后，再关闭网络拦截器
                    try:
                        interceptor.close(deadline=deadline)
                    except Exception as exc:
                        errors.append(str(exc))
                if planned_network:
                    # 最后移除本次任务创建的 Docker 网络
                    try:
                        self._remove_resource("network", network_name, deadline=deadline)
                    except Exception as exc:
                        errors.append(str(exc))
                if errors:
                    cleanup_error = DockerCleanupError("; ".join(errors))
                    raise cleanup_error

        try:
            agent_environment = dict(config.environment)
            network_arguments: list[str]
            if interception is not None:
                # 这里走网络拦截路径：记录 trace 状态，并创建任务网络
                trace_state = InterceptionTraceState()
                self._require_non_root_image(image, deadline=preparation)
                self._plan_resource("network", network_name, "network", suffix)
                planned_network = True
                self._create_resource("network", network_name,
                                      ["network", "create", *self._labels("network", suffix), network_name],
                                      deadline=preparation)
                # 这里启动网络拦截器，后续 Agent 的流量经过它
                interceptor, token_environment = self._start_interceptor(
                    agent_id=config.agent_id,
                    interception=interception,
                    suffix=suffix,
                    network_name=network_name,
                    trace_state=trace_state,
                    deadline=preparation,
                )
                agent_environment.update(interception.environment)
                agent_environment.update(token_environment)
                # 配置证书信任，让 Agent 能通过拦截器访问 HTTPS 服务
                certificate_target = "/run/defuzex-ca/ca.pem"
                agent_environment.update(
                    get_trust_plugin(interception.trust_plugin).agent_environment(
                        certificate_target
                    )
                )
                # Agent 与拦截器共享网络空间
                network_arguments = [
                    "--network",
                    f"container:{interceptor.container_name}",
                ]
            else:
                # 没有拦截配置时，创建不能直接访问外网的内部网络
                self._plan_resource("network", network_name, "network", suffix)
                planned_network = True
                self._create_resource("network", network_name,
                                      ["network", "create", "--internal", *self._labels("network", suffix), network_name],
                                      deadline=preparation)
                network_arguments = ["--network", network_name]

            # 组装 docker create 参数；此时还没有启动 Agent 容器
            command = [
                "create",
                "--init",
                "--name",
                agent_name,
                *self._labels("agent", suffix),
                *network_arguments,
                "--workdir",
                config.workdir,
                *self._policy.run_arguments(),
            ]
            if interceptor is not None:
                # 把拦截器证书挂载进 Agent 容器
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
                # 把宿主输入目录和可写的结果目录挂载给 worker
                inputs, outputs = invocation
                command.extend(("--mount", _bind_mount(inputs, "/run/abb-input")))
                # All other filesystem locations retain the existing read-only policy.
                command.extend(("--mount", f"type=bind,source={outputs},target=/run/abb-output"))
            # 禁止生成 Python 缓存，并让日志及时输出
            agent_environment.update(
                PYTHONDONTWRITEBYTECODE="1",
                PYTHONUNBUFFERED="1",
            )
            # 把环境变量、镜像和启动命令加入容器参数
            for key, value in sorted(agent_environment.items()):
                command.extend(("--env", f"{key}={value}"))
            command.extend((image, *config.argv))

            # 登记并创建 Agent 容器，便于失败时找到它并清理
            self._plan_resource("container", agent_name, "agent", suffix)
            planned_agent = True
            self._create_resource("container", agent_name, command, deadline=preparation)
            preparation.check()
            
            # 这里真正启动 Agent 容器，并接收 stdout/stderr 日志
            # Kuma 评测的 config.argv 指向 Kuma worker，由它决定生成还是执行 Case
            process = self._commands.start(
                ["start", "--attach", agent_name], control=self.control,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            # 包装成会话，供上层等待结束、检查 trace、关闭和清理资源。
            session = DockerSession(
                process,
                close_callback=cleanup,
                control=self.control,
                default_timeout=self._timeout_override or config.timeout_sec,
                runtime_error_checker=trace_state.check_persistence if trace_state is not None else None,
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
            self.control.check()
            return session
        except BaseException as original:
            # 启动中途失败，也要回收已经创建的容器、拦截器和网络。
            try:
                if session is not None:
                    session.close()
                else:
                    cleanup()
            except DockerCleanupError as exc:
                raise exc from original
            finally:
                if process is not None and session is None:
                    DockerCommandRunner.terminate(process)
            raise

    def _start_interceptor(
        self,
        *,
        agent_id: str,
        interception: InterceptionConfig,
        suffix: str,
        network_name: str,
        trace_state: InterceptionTraceState,
        deadline: Deadline | None = None,
    ) -> tuple[RunningModelInterceptor, dict[str, str]]:
        if deadline is not None:
            deadline.check()
        if isinstance(self._interceptor_images, LocalInterceptorImageProvider):
            image = self._interceptor_images.resolve_image(deadline=deadline, log_directory=self._build_logs())
        else:
            image = self._interceptor_images.resolve_image()
        # Explicit/static images must already be available; hidden Docker pulls
        # inside run would escape the single build preparation policy.
        self._run("image", "inspect", image, deadline=deadline)
        container_name = f"defuzex-{suffix}-interceptor"
        secret_dir = Path(tempfile.mkdtemp(prefix="defuzex-model-interceptor-"))
        config_file = secret_dir / "interceptor_config.json"
        ca_dir = secret_dir / "ca"
        ca_certificate = ca_dir / "mitmproxy-ca-cert.pem"
        planned = False
        log_process = None
        trace_reader = None
        try:
            ca_dir.mkdir()
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
                        "tool_routes": [
                            {"host_patterns": list(route.host_patterns), "ports": list(route.ports),
                             "methods": list(route.methods), "path_patterns": list(route.path_patterns),
                             "purpose": route.purpose}
                            for route in interception.tool_routes
                        ],
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

            command = [
                "run",
                "--detach",
                "--init",
                "--name",
                container_name,
                *self._labels("interceptor", suffix),
                "--network",
                network_name,
                *self._interceptor_policy.run_arguments(),
                "--mount",
                _bind_mount(config_file, "/run/secrets/interceptor_config"),
            ]
            for path in sorted(secret_dir.glob("*.token")) + sorted(
                secret_dir.glob("*.secret")
            ):
                command.extend(
                    ("--mount", _bind_mount(path, f"/run/secrets/{path.name}"))
                )
            command.append(image)
            self._plan_resource("container", container_name, "interceptor", suffix)
            planned = True
            self._create_resource("container", container_name, command, deadline=deadline)
            self._wait_for_interceptor(container_name, ca_certificate, deadline=deadline)
            if not ca_certificate.is_file():
                raise DockerRuntimeError("Model interceptor CA was not exported")
            log_process, trace_reader = self._follow_trace(container_name, trace_state)
            self.control.check()
        except BaseException as original:
            try:
                if planned:
                    self._remove_resource("container", container_name)
            except DockerCleanupError as exc:
                raise exc from original
            finally:
                if log_process is not None:
                    DockerCommandRunner.terminate(log_process)
                if trace_reader is not None:
                    trace_reader.join(timeout=2)
                shutil.rmtree(secret_dir, ignore_errors=True)
            raise

        def close_interceptor(deadline: Deadline | None = None) -> None:
            try:
                if not self.control.forced:
                    try:
                        self._commands.run(["container", "stop", "--time", "2", container_name],
                                           cleanup=True, timeout=4, deadline=deadline)
                    except Exception:
                        pass  # The removal command determines cleanup success.
                self._remove_resource("container", container_name, deadline=deadline)
            finally:
                shutil.rmtree(secret_dir, ignore_errors=True)

        return (
            RunningModelInterceptor(
                container_name=container_name,
                ca_certificate=ca_certificate,
                _close_callback=close_interceptor,
                _log_process=log_process,
                _trace_reader=trace_reader,
                _close_with_deadline=close_interceptor,
            ),
            token_environment,
        )

    def _follow_trace(
        self, container_name: str, trace_state: InterceptionTraceState
    ) -> tuple[subprocess.Popen[str], threading.Thread]:
        process = self._commands.start(
            ["logs", "--follow", container_name], control=self.control,
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
            try:
                for line in process.stdout:
                    event = TraceEvent.from_log_line(line.rstrip("\r\n"))
                    if event is not None:
                        # A pair is complete only after its full event is saved.
                        self._trace_sink.emit(event)
                        trace_state.emit(event)
            except Exception as exc:
                trace_state.fail(exc)
            finally:
                process.stdout.close()

        reader = threading.Thread(
            target=consume,
            daemon=True,
            name=f"{container_name}-trace",
        )
        reader.start()
        return process, reader

    def _required_trace_callback(
        self,
        trace_state: InterceptionTraceState,
    ) -> Callable[[object], None]:
        def require_trace(value: object) -> None:
            checkpoint = int(value)
            if not trace_state.wait_for_completion_after(checkpoint, timeout=2, control=self.control):
                raise DockerRuntimeError(
                    "Agent invocation trace was not accepted: " + trace_state.diagnostic()
                )
            if not trace_state.wait_for_idle(control=self.control):
                raise DockerRuntimeError("Model trace is incomplete: " + trace_state.diagnostic())

        return require_trace

    def _wait_for_interceptor(
        self, container_name: str, ca_certificate: Path, *, deadline: Deadline | None = None,
    ) -> None:
        startup = Deadline.after(self._limits.startup_seconds)
        deadline = startup if deadline is None else Deadline(min(startup.expires_at, deadline.expires_at))
        while deadline.remaining():
            self.control.check()
            logs = self._run_quiet("logs", container_name, capture=True, deadline=deadline)
            if (
                logs is not None
                and '"event": "interceptor_ready"' in logs.stdout
            ):
                self._export_ca(container_name, ca_certificate, deadline=deadline)
                return
            state = self._run_quiet(
                "inspect",
                "--format",
                "{{.State.Running}}",
                container_name,
                capture=True,
                deadline=deadline,
            )
            if state is not None and state.stdout.strip() == "false":
                detail = logs.stdout.strip() if logs is not None else ""
                raise DockerRuntimeError(
                    f"Model interceptor stopped during startup{': ' + detail if detail else ''}"
                )
            self.control.wait(min(0.25, deadline.remaining()))
        raise DockerRuntimeError(
            "Model interceptor did not become ready within its startup budget"
        )

    def _export_ca(self, container_name: str, destination: Path, *, deadline: Deadline | None = None) -> None:
        """Copy only the public CA; private key stays in interceptor tmpfs."""
        import ssl
        # Docker's archive/cp endpoint cannot reliably read a live tmpfs mount.
        # Read the single public PEM through exec; never export the CA directory.
        pem = self._run("exec", container_name, "cat", "/run/defuzex/ca/mitmproxy-ca-cert.pem", deadline=deadline).stdout
        if "PRIVATE KEY" in pem or "-----BEGIN CERTIFICATE-----" not in pem:
            raise DockerRuntimeError("Invalid interceptor public CA export")
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=pem)
        stream = tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=destination.parent, delete=False)
        owned = Path(stream.name)
        try:
            with stream:
                stream.write(pem)
            # Windows cannot replace or remove a file while this handle is open.
            owned.chmod(0o644)
            owned.replace(destination)
        finally:
            owned.unlink(missing_ok=True)

    def _require_non_root_image(self, image: str, *, deadline: Deadline | None = None) -> None:
        result = self._run(
            "image", "inspect", "--format", "{{.Config.User}}", image, deadline=deadline,
        )
        user = result.stdout.strip()
        if not user or user in {"0", "root", "0:0", "root:root"}:
            raise DockerRuntimeError(
                "Transparent interception requires an Agent image with a non-root USER"
            )

    def _check_available(self, *, deadline: Deadline | None = None) -> None:
        try:
            result = self._run_quiet("info", "--format", "{{.ServerVersion}}", capture=True, deadline=deadline)
        except DockerCommandTimeout as exc:
            raise DockerUnavailableError("Docker daemon availability check timed out") from exc
        if result is None or result.returncode != 0:
            detail = result.stderr.strip() if result is not None else "docker not found"
            raise DockerUnavailableError(f"Docker daemon is unavailable: {detail}")

    def _run(self, *args: str, deadline: Deadline | None = None) -> subprocess.CompletedProcess[str]:
        result = self._run_quiet(*args, capture=True, deadline=deadline)
        if result is None:
            raise DockerRuntimeError("Docker executable was not found")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise DockerRuntimeError(f"Docker command failed: {detail}")
        return result

    def _run_quiet(
        self, *args: str, capture: bool = False, deadline: Deadline | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        try:
            return self._commands.run(
                args, control=self.control, timeout=self._limits.command_seconds,
                deadline=deadline,
            )
        except FileNotFoundError:
            return None

    def _build_logs(self) -> Path | None:
        return self.artifact_root / "docker-build" if self.artifact_root is not None else None

    def _resource_identity(self, role: str, suffix: str) -> dict[str, object]:
        return {
            "suite_id": self.identity.get("suite_id") or self.run_id or suffix,
            "job_id": self.identity.get("job_id") or self.run_id or suffix,
            "artifact_run_id": self.identity.get("artifact_run_id") or self.run_id or suffix,
            "role": role,
        }

    def _labels(self, role: str, suffix: str) -> list[str]:
        return [part for key, value in self._resource_identity(role, suffix).items()
                for part in ("--label", f"abb.{key}={value}")]

    def _plan_resource(self, kind: str, name: str, role: str, suffix: str) -> None:
        self._resources.plan(kind, name, self._resource_identity(role, suffix))

    def _create_resource(self, kind: str, name: str, arguments: list[str], *, deadline: Deadline | None) -> None:
        try:
            created = self._run(*arguments, deadline=deadline)
        except BaseException as exc:
            if getattr(exc, "docker_client_interrupted", False):
                self._uncertain_resources.add((kind, name))
            raise
        self._resources.created(kind, name, created.stdout.strip())

    def _remove_resource(self, kind: str, name: str, *, deadline: Deadline | None = None) -> None:
        deadline = deadline or Deadline.after(self._limits.cleanup_seconds)
        try:
            arguments = [kind, "rm", *(["--force"] if kind == "container" else []), name]
            removed = self._commands.run(arguments, cleanup=True, timeout=15, deadline=deadline)
            if removed.returncode != 0:
                # An interrupted creation may have left nothing. Only explicit
                # absence is success; daemon/network errors must remain visible.
                detail = (removed.stderr or removed.stdout).strip()
                missing = "no such container" if kind == "container" else "no such network"
                if missing not in detail.lower() and not (kind == "network" and "not found" in detail.lower() and name in detail):
                    raise DockerCleanupError(f"Could not remove owned {kind} {name}: {detail}")
                if (kind, name) in self._uncertain_resources:
                    raise DockerCleanupError(
                        f"Creation of {kind} {name} was interrupted and the daemon reports absence; "
                        "a delayed create cannot be ruled out"
                    )
            self._uncertain_resources.discard((kind, name))
            self._resources.removed(kind, name)
        except Exception as exc:
            self._resources.failed(kind, name, str(exc))
            if isinstance(exc, DockerCleanupError):
                raise
            raise DockerCleanupError(f"Could not confirm removal of {kind} {name}: {exc}") from exc


def _bind_mount(source: Path, target: str) -> str:
    return f"type=bind,source={source.resolve()},target={target},readonly"


def _writable_bind_mount(source: Path, target: str) -> str:
    return f"type=bind,source={source.resolve()},target={target}"

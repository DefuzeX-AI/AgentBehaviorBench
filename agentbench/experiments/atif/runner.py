"""Configured acceptance runs using ABB's existing runtime and adapter factory."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4
import json
import os
import tomllib

from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.harness.registry import load_registry
from agentbench.observe.store import TraceStore, environment_secrets, redact
from agentbench.runtime.contracts.execution import RunControl, RunCancelled
from agentbench.runtime.docker import DockerRuntime, DockerPolicy
from agentbench.runtime.factory import RuntimeFactory
from agentbench.runtime.source import prepare_agent_source
from agentbench.sdk.common.workspace import workspace_policy, prepare_workspace
from agentbench.trajectory.metadata import capture_target
from agentbench.trajectory.atif.export import export_run, save_json
from .acceptance import verify, live_checks


@dataclass(frozen=True)
class WorkspacePolicy(DockerPolicy):
    host: str = ""
    target: str = ""
    extra_mounts: tuple = ()

    def run_arguments(self):
        args = (*super().run_arguments(), "--mount", f"type=bind,source={self.host},target={self.target}")
        for source, target in self.extra_mounts:
            args += ("--mount", f"type=bind,source={source},target={target},readonly")
        return args


def run_experiment(config_path, output, *, names=None, bundle=False):
    config_path = Path(config_path).resolve()
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    if names:
        unknown = set(names) - {case["name"] for case in config["cases"]}
        if unknown:
            raise ValueError("Unknown configured experiment case")
        config["cases"] = [case for case in config["cases"] if case["name"] in names]
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Experiment directory must be new or empty")
    output.mkdir(parents=True, exist_ok=True)
    registry = load_registry(config_path.parent / config["registry"])
    environment = dict(os.environ)
    for key, reference in config.get("environment_refs", {}).items():
        if not environment.get(reference):
            raise ValueError(f"Required environment reference is unset: {reference}")
        environment[key] = environment[reference]
    environment.update(config.get("environment", {}))
    secrets = environment_secrets(environment)
    results = []
    for case in config["cases"]:
        attempts = case.get("attempts", 1)
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("Explicit experiment attempts must be between 1 and 3")
        for attempt in range(attempts):
            agent = registry.find(case["agent_id"], enabled_only=False)
            run_id = uuid4().hex
            directory = output / run_id
            directory.mkdir(mode=0o700)
            (directory / "request").mkdir()
            manifest = tomllib.loads((agent.path / "agent.toml").read_text(encoding="utf-8"))
            policy = workspace_policy(manifest)
            if not policy.path:
                raise ValueError("File experiment requires a declared Agent workspace")
            workspace = directory / "actual-files"
            prepare_workspace(agent.path, workspace, policy)
            workspace.chmod(0o777)
            relative = PurePosixPath(case["task_directory"])
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError("Task directory must be relative to the declared workspace")
            task_root = workspace.joinpath(*relative.parts)
            task_root.mkdir(parents=True, exist_ok=True)
            task_root.chmod(0o777)
            prompt_path = config_path.parent / case["prompt"]
            prompt = prompt_path.read_text(encoding="utf-8").replace("{{task_directory}}", str(PurePosixPath(policy.path) / relative))
            input_key = manifest.get("adapter", {}).get("input_key")
            value = {input_key: prompt} if input_key else prompt
            save_json(directory / "request/target.json", capture_target(agent.path))
            mounts = []
            for number, override in enumerate(case.get("native_config_overrides", [])):
                import yaml
                source_path = config_path.parent / override["source"]
                native_config = yaml.safe_load(source_path.read_text(encoding="utf-8"))
                for dotted, configured_value in override["values"].items():
                    keys = dotted.split(".")
                    section = native_config
                    for part in keys[:-1]:
                        section = section[part]
                    section[keys[-1]] = configured_value
                destination = directory / "request" / f"native-config-{number}.yaml"
                destination.write_text(yaml.safe_dump(native_config, allow_unicode=True), encoding="utf-8")
                mounts.append((str(destination), override["target"]))
            save_json(directory / "request/experiment.json", {"case": case, "attempt": attempt + 1,
                "workspace": policy.as_dict(), "prompt": prompt,
                "provider": environment.get("ABB_MODEL_PROVIDER"), "model": environment.get("OPENROUTER_MODEL")})
            state = {"schema": "abb.observe.run.v1", "run_id": run_id, "agent_id": agent.agent_id,
                "status": "running", "input": value}
            save_json(directory / "run.json", state)
            control = RunControl()
            store = TraceStore(directory / "network.jsonl", run_id, source="interceptor", environ=environment)
            cancel_after = case.get("cancel_after_deltas")

            class Sink:
                count = 0
                def emit(self, event):
                    store.emit(event)
                    if event.event == "llm_delta":
                        self.count += 1
                        if cancel_after and self.count >= cancel_after:
                            control.cancel()

            sink = Sink()
            runtime = DockerRuntime(environ=environment, trace_sink=sink, artifact_root=directory,
                policy=WorkspacePolicy(host=str(workspace), target=policy.path, extra_mounts=tuple(mounts)),
                timeout_sec=case.get("timeout", 600), run_id=run_id, control=control)
            adapter = RuntimeFactory(docker_builder=lambda: runtime).create_adapter(agent, adapter_factory=DEFAULT_ADAPTER_FACTORY)
            print(f"ATIF experiment: {case['name']} attempt {attempt + 1}; artifacts: {directory}", flush=True)
            try:
                prepare_agent_source(agent.path, output_fn=lambda message: print(message, flush=True))
                adapter.load()
                invocation = adapter.invoke(value, run_config=case.get("run_config"))
                state.update(status="succeeded", output=redact(invocation.output, secrets))
            except (Exception, KeyboardInterrupt) as exc:
                state.update(status="cancelled" if isinstance(exc, (RunCancelled, KeyboardInterrupt)) else "failed",
                    error_type=type(exc).__name__, error=redact(str(exc), secrets))
            finally:
                try:
                    adapter.close()
                    state["cleanup_status"] = "completed"
                except Exception as exc:
                    state.update(cleanup_status="failed", cleanup_error=redact(str(exc), secrets))
                state["observed_deltas"] = sink.count
                save_json(directory / "run.json", state)
            exported = output / (run_id + "-atif")
            try:
                if bundle:
                    from agentbench.trajectory.atif.bundle import export_bundle
                    from agentbench.trajectory.atif.export import build_export
                    portable = export_bundle(directory, output / "bundles", adapters=case.get("adapters", []),
                        evidence_files=["actual-files/" + f["path"] for f in case.get("files", []) if (workspace / f["path"]).is_file()])
                    result, _ = build_export(directory, adapters=case.get("adapters", []))
                    checks = live_checks(directory, result, case)
                    checks["portable_bundle_verified"] = portable["validation"]["passed"]
                    exported = Path(portable["path"])
                else:
                    result = export_run(directory, exported, adapters=case.get("adapters", []))
                    checks = live_checks(directory, result, case)
                    verified = verify(directory, exported)
                    checks["rebuild_matches"] = verified["passed"]
                item = {"case": case["name"], "run_id": run_id, "checks": checks,
                    "coverage": result.validation, "export": str(exported), "passed": all(checks.values())}
            except Exception as exc:
                item = {"case": case["name"], "run_id": run_id, "passed": False,
                        "error_type": type(exc).__name__, "error": redact(str(exc), secrets)}
            results.append(item)
            save_json(output / "acceptance-report.json", {"passed": all(r["passed"] for r in results), "runs": results})
    return {"passed": all(r["passed"] for r in results), "runs": results}

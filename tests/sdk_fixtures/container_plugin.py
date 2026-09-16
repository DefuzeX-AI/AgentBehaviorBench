"""Test-only directory adapter; never registered in the production SDK folder."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agentbench.adapter import AdapterInvocation
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.sdk.contracts import PreparedCase
from agentbench.runtime.docker.policy import DockerPolicy


@dataclass(frozen=True)
class Report:
    status: str
    confidence: object
    issues: tuple
    evidence_gaps: tuple


class Runner:
    def __init__(self, options):
        self.image = options["image"]
        self.fixtures = Path(options["fixtures"]).resolve()
        self.output_root = Path(options["output"]).resolve()

    def validate_sdk(self, registration):
        subprocess.run(
            ["docker", "image", "inspect", self.image], check=True, capture_output=True
        )
        return "offline-custom-container"

    def prepare_cases(self, registration, *, on_progress=None):
        return tuple(PreparedCase(index) for index in range(registration.case_count))

    def run_case(self, registration, case, **callbacks):
        output = self.output_root / f'case-{case.case_index:04d}'
        output.mkdir(parents=True, exist_ok=True)
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--user",
            "10001:10001",
            *DockerPolicy().run_arguments(),
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "KUMA_API_KEY=",
            "--env",
            "DEFUZEX_API_KEY=",
            "--mount",
            f"type=bind,source={self.fixtures},target=/checks,readonly",
            "--mount",
            f"type=bind,source={output},target=/artifacts",
            "--entrypoint",
            "python",
            self.image,
            "/checks/container_run.py",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output / "container.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        if result.returncode:
            raise RuntimeError(
                f"Offline container failed; see {output / 'container.log'}"
            )
        record = json.loads((output / "run.json").read_text())
        step = BenchmarkStepResult(
            record["input_id"],
            record["payload"],
            AdapterInvocation(output=record["output"], raw_output=record["output"]),
        )
        if callbacks.get("on_step_start"):
            callbacks["on_step_start"](
                registration.agent_id, step.input_id, step.payload
            )
        if callbacks.get("on_step_complete"):
            callbacks["on_step_complete"](registration.agent_id, step)
        report = record["report"]
        return BenchmarkResult(
            registration.agent_id,
            "offline-container-echo",
            record["run_id"],
            record["state"],
            Report(
                report["status"],
                report.get("confidence"),
                tuple(report.get("issues", ())),
                tuple(report.get("evidence_gaps", ())),
            ),
            (step,),
            record["history_count"],
            provider_mode="offline-custom-container",
        )


class Adapter:
    execution = "container"

    def create_benchmark_runner(self, *, context, options):
        return Runner(options)


plugin = Adapter()

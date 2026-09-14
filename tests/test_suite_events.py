"""Worker event snapshots and identity survive interleaved SDK callbacks."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import threading
from types import MappingProxyType, SimpleNamespace

from agentbench.adapter import AdapterInvocation
from agentbench.harness.events import EventBus, QueuedTraceSink
from agentbench.harness.jobs import CaseJob, PreparationJob, SuiteCallbacks, run_case_job, run_preparation_job
from agentbench.harness.progress import BenchmarkProgress
from agentbench.harness.result import BenchmarkResult, BenchmarkStepResult
from agentbench.runtime.contracts.execution import RunControl
from agentbench.runtime.interception import TraceEvent
from agentbench.sdk.contracts import PreparedCase


@dataclass(frozen=True, slots=True)
class ImmutableReport:
    status: str
    extensions: object


def test_worker_snapshot_preserves_dataclasses_and_detaches_immutable_mappings():
    received, callbacks, thread_ids = [], [], []
    owner = threading.get_ident()
    bus = EventBus(on_event=lambda event: received.append(event), capacity=4)
    original = {"messages": ["before"]}
    payload = MappingProxyType(original)
    step = BenchmarkStepResult("one", payload, AdapterInvocation(payload, {"input": payload}))
    report = ImmutableReport("pass", MappingProxyType({"nested": payload}))

    def callback(value):
        callbacks.append(value)
        thread_ids.append(threading.get_ident())

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(bus.publish, {"event": "step_completed", "step": step, "report": report},
                    callback, (step,)).result(timeout=2)
    original["messages"].append("after")
    bus.drain()
    assert thread_ids == [owner]
    assert isinstance(callbacks[0], BenchmarkStepResult)
    assert isinstance(received[0]["report"], ImmutableReport)
    assert callbacks[0].payload == {"messages": ["before"]}
    assert received[0]["report"].extensions["nested"] == {"messages": ["before"]}
    received[0]["step"].payload["messages"].append("consumer mutation")
    assert callbacks[0].payload == {"messages": ["before"]}
    assert original == {"messages": ["before", "after"]}


def test_preview_keeps_late_identity_fields_and_separates_same_call_across_cases():
    delivered = []
    bus = EventBus()
    sink = QueuedTraceSink(bus, SimpleNamespace(emit=delivered.append),
                           {"suite_id": "suite", "job_id": "job-a", "agent_id": "trusted-a"})
    for case in (0, 1):
        data = {f"filler-{index}": "x" * 1000 for index in range(20)}
        data.update(agent_id="forged", job_id="forged", artifact_run_id=f"run-{case}",
                    case_index=case, case_id=f"case-{case}", call_id="same-call",
                    provider="model", payload={"prompt": f"question-{case}"})
        sink.emit(TraceEvent("llm_request", data))
    bus.drain()
    assert len(delivered) == 2
    assert [event.data["artifact_run_id"] for event in delivered] == ["run-0", "run-1"]
    assert [event.data["case_index"] for event in delivered] == [0, 1]
    assert delivered[1].data["payload"]["prompt"] == "question-1"
    assert all(event.data["agent_id"] == "trusted-a" and event.data["job_id"] == "job-a"
               and event.data["call_id"] == "same-call" for event in delivered)
    assert len(delivered[0].data["filler-0"]) == 512


def test_preparation_and_cases_have_separate_artifact_context_and_trusted_identity():
    events, progress = [], []
    bus = EventBus(on_event=events.append)
    agent = SimpleNamespace(agent_id="a", case_count=2)

    class Runner:
        def prepare_cases(self, registration, **kwargs):
            emit = kwargs["on_progress"]
            emit(BenchmarkProgress("case_generation", "started"))
            emit(BenchmarkProgress("case_generation", "succeeded", artifact_run_id="generation-run"))
            return (PreparedCase(0, "case-0"), PreparedCase(1, "case-1"))

        def run_case(self, registration, case, **kwargs):
            emit = kwargs["on_progress"]
            emit(BenchmarkProgress("benchmark_execution", "started", job_id="forged",
                                   case_index=999, case_id="forged"))
            kwargs["on_step_start"]("a", "input-1", {"text": "hello"})
            return BenchmarkResult("a", "fixture", "run", "done", None, (), 0)

    identity = {
        "suite_id": "suite", "job_id": "job-a", "agent_id": "a", "registration_index": 0,
        "phase": "generate", "case_index": None, "case_id": None,
    }
    callbacks = SuiteCallbacks(total=1, on_progress=progress.append)
    prepared = run_preparation_job(PreparationJob(agent, Runner(), identity),
                                   control=RunControl(), bus=bus, callbacks=callbacks)
    assert prepared.error is None
    for case in prepared.cases:
        outcome = run_case_job(CaseJob(agent, Runner(), case, {
            **identity, "agent_job_id": identity["job_id"], "job_id": f"job-case-{case.case_index}",
            "phase": "execute", "case_index": case.case_index, "case_id": case.case_id,
        }), control=RunControl(), bus=bus, callbacks=callbacks)
        assert outcome.result.benchmark is not None
    assert [event.case_index for event in progress if event.stage == "benchmark_execution"] == [0, 1]
    assert all(event.case_index is None for event in progress if event.stage == "case_generation")
    steps = [event for event in events if event["event"] == "step_started"]
    assert [event["case_index"] for event in steps] == [0, 1]
    assert all("artifact_run_id" not in event for event in steps)
    assert all(event.agent_id == "a" for event in progress)
    assert [event["job_id"] for event in steps] == ["job-case-0", "job-case-1"]
    assert [event["case_id"] for event in steps] == ["case-0", "case-1"]

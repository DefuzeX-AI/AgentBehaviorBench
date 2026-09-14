"""Mutable per-Agent scheduling state, owned exclusively by its coordinator."""

from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import uuid4

from agentbench.harness.jobs import PreparationJob
from agentbench.harness.result import CaseResult, EvaluationFailure, SuiteAgentResult
from agentbench.sdk.contracts import PreparedCase


@dataclass
class AgentSeed:
    """Validated durable state used to skip completed work after a restart."""
    prepared: dict[int, PreparedCase] = field(default_factory=dict)
    results: dict[int, CaseResult] = field(default_factory=dict)
    attempts: dict[int, int] = field(default_factory=dict)
    recoveries: dict[int, CaseResult] = field(default_factory=dict)
    retries: dict[int, int] = field(default_factory=dict)
    retry_at: dict[int, float] = field(default_factory=dict)
    waiting_results: dict[int, CaseResult] = field(default_factory=dict)


@dataclass
class AgentState:
    preparation: PreparationJob
    started: bool = False
    completed: bool = False
    preparation_error: EvaluationFailure | None = None
    pending: deque = field(default_factory=deque)
    results: dict = field(default_factory=dict)
    identities: dict = field(default_factory=dict)
    prepared: dict = field(default_factory=dict)
    attempts: dict = field(default_factory=dict)
    retries: dict = field(default_factory=dict)
    recoveries: dict = field(default_factory=dict)
    waiting_results: dict = field(default_factory=dict)

    def __post_init__(self):
        parent = self.preparation.identity
        self.identities = {index: MappingProxyType({**parent, 'job_id': f'case_{uuid4().hex}',
            'agent_job_id': parent['job_id'], 'phase': 'execute', 'case_index': index, 'case_id': None})
            for index in range(self.preparation.registration.case_count)}

    def initialize(self, seed: AgentSeed):
        self.results.update(seed.results)
        self.prepared.update(seed.prepared)
        self.attempts.update(seed.attempts)
        self.recoveries.update(seed.recoveries)
        self.retries.update(seed.retries)
        self.waiting_results.update(seed.waiting_results)
        self.started = bool(seed.results or seed.prepared)
        for index, case in sorted(seed.prepared.items()):
            if index not in self.results:
                self.pending.append(case)
            self.identities[index] = MappingProxyType({**self.identities[index], 'case_id': case.case_id})

    def begin_attempt(self, case):
        index = case.case_index
        previous = self.recoveries.get(index)
        number = previous.attempt_number if previous else self.attempts.get(index, 0) + 1
        self.attempts[index] = number
        self.identities[index] = MappingProxyType({**self.identities[index],
            'job_id': self.identities[index]['job_id'] if number == 1 and not previous else f'case_{uuid4().hex}',
            'attempt_id': previous.attempt_id if previous else uuid4().hex,
            'attempt_number': number, 'case_id': case.case_id,
            'recovery_action': 'resume_request' if previous else 'execute'})
        return self.identities[index]

    def snapshot(self):
        return SuiteAgentResult(self.preparation.registration.agent_id,
            tuple(self.results[index] for index in sorted(self.results)),
            self.preparation.registration.case_count, self.preparation_error)

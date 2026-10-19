"""Small concrete implementations of the existing SDKRun/input/report contracts.

Use these for simple SDKs or provide structural equivalents. A custom get_input
may choose its next input from history; only the current input reaches the Agent.
"""
from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class Input:
    input_id: str
    payload: object


@dataclass(frozen=True)
class Report:
    status: str
    confidence: object = None
    issues: tuple = ()
    evidence_gaps: tuple = ()


class Run:
    """Optional defaults for fixed-input Cases; override SDK business methods.

    ``case`` remains a generation snapshot. Mutable execution state belongs in
    history or SDK-owned fields. ``evidence`` exposes recorded step directories
    and original transported spans to submit/judge without vendor-specific APIs.
    """
    def __init__(self, case, *, evidence=None):
        self.case = deepcopy(case)
        self.run_id = uuid4().hex
        self.state = 'ready'
        self.report = None
        self.history = ()
        self.evidence = evidence
        self._current = None

    def get_input(self, *, full=False):
        if self._current is not None:
            raise ValueError('Submit the current input before requesting another')
        inputs = self.case['inputs']
        if len(self.history) == len(inputs):
            self.state = 'completed'
            return None
        item = inputs[len(self.history)]
        self._current = Input(item['input_id'], item['payload'])
        self.state = 'input_delivered'
        return self._current

    def submit(self, output=None, *, status='completed', error=None):
        if self._current is None:
            raise ValueError('There is no current input to submit')
        self.history += ({'input_id': self._current.input_id, 'output': output,
                          'status': status, 'error': error},)
        self._current = None
        self.state = 'ready'
        return self.report

    def judge(self):
        raise NotImplementedError('Implement this SDK\'s Judge and return an SDKReport')

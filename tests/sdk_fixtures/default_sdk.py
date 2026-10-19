"""Four business methods; no custom worker, runner, or vendor import."""
import importlib.abc
import sys

from agentbench.sdk.integration.run import Input, Report, Run


class RejectKuma(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'kuma' or fullname.startswith(('kuma.', 'agentbench.sdk.plugin.kuma')):
            raise AssertionError('Default SDK execution imported Kuma: ' + fullname)


class EchoRun(Run):
    def get_input(self, *, full=False):
        if len(self.history) == 2:
            self.state = 'completed'
            return None
        # The second input depends on the actual first output. It is not a
        # precomputed input copied from the Case by ABB.
        payload = self.case['first'] if not self.history else self.history[0]['output']
        self._current = Input(str(len(self.history) + 1), payload)
        self.state = 'input_delivered'
        return self._current

    def submit(self, output=None, *, status='completed', error=None):
        return super().submit(output, status=status, error=error)

    def judge(self):
        outputs = [entry['output'] for entry in self.history]
        assert outputs == ['first:1', 'first:1:2'], outputs
        spans = list(self.evidence.spans())
        assert spans and all(span.context.is_valid for span in spans)
        self.report = Report('pass', 1.0)
        return self.report


def create_run(*, case=None, case_index=0, **context):
    assert not any(name == 'kuma' or name.startswith(('kuma.', 'agentbench.sdk.plugin.kuma')) for name in sys.modules)
    if not any(isinstance(finder, RejectKuma) for finder in sys.meta_path):
        sys.meta_path.insert(0, RejectKuma())
    if case is None:
        # A real SDK calls its Case generator here, with repo_path/agent_root.
        case = {'case_id': f'default-case-{case_index}', 'first': 'first',
                'criteria': 'Keep Agent state across two turns; second input uses the first output.'}
    return EchoRun(case, evidence=context['evidence'])

"""Real SDK and real Agent execution, with deterministic offline judgment."""
from uuid import uuid4
from dataclasses import dataclass
from agentbench.sdk.plugin.kuma.worker import main


def case_provider(context):
    return {'case_id': 'private-' + uuid4().hex, 'input_type': 'text', 'inputs': [
        {'input_id': 'one', 'payload_type': 'text', 'payload': 'inspect workspace'},
        {'input_id': 'two', 'payload_type': 'text', 'payload': 'future-' + uuid4().hex}]}


class Cases:
    agent_profile_required = False

    def generate_case(self, context):
        return case_provider(context)


def judge(context):
    assert context.history[0].submission.output == 'first step isolated'
    assert context.history[1].submission.output.startswith('future-')
    assert context.history[0].submission.extensions['trace_evidence']['spans']
    return {'status': 'pass', 'summary': 'Isolated two-turn execution', 'issues': []}


@dataclass(frozen=True)
class Providers:
    name: str = 'offline-isolation'
    max_steps: int = 2

    @staticmethod
    def case_options(index):
        return {'case_provider': Cases(), 'judge': False}

    @staticmethod
    def judge_provider(output):
        return judge


if __name__ == '__main__':
    raise SystemExit(main(Providers()))

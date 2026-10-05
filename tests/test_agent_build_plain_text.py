"""Text Cases must not be forced through an unconditional JSON decoder."""
import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.frameworks.langgraph.binding_validation import validate_binding
from tests.test_agent_build_input_boundary import configure
from tests.agent_build_fixtures import source


def binding(parser):
    return 'import json\n' + parser + '''
class Workflow:
    def invoke(self, value, config=None):
        return parse_problem(value)
def create_graph():
    return Workflow()
'''


@pytest.mark.parametrize('parser', [
    'def parse_problem(value):\n    return json.loads(value)\n',
    '''def parse_problem(value):
    try:
        spec = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("requires a valid JSON problem object") from exc
    return spec
''',
])
def test_json_only_helper_cannot_accept_plain_text_cases(source, parser):
    with pytest.raises(BuildError, match='plain text'):
        validate_binding(binding(parser), configure(source))


def test_direct_json_only_invoke_is_rejected(source):
    content = '''from json import loads as decode
class Workflow:
    def invoke(self, value, config=None):
        return decode(value)
def create_graph():
    return Workflow()
'''
    with pytest.raises(BuildError, match='plain text'):
        validate_binding(content, configure(source))


@pytest.mark.parametrize('parser', [
    '''def parse_problem(value):
    if value.lstrip().startswith('{'):
        return json.loads(value)
    return {"questions": [value]}
''',
    '''def parse_problem(value):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"questions": [value]}
''',
    '''def parse_problem(value):
    template = json.loads('{"questions": []}')
    template['questions'] = [value]
    return template
''',
    '''def parse_problem(value):
    if not value.lstrip().startswith('{'):
        return {"questions": [value]}
    return json.loads(value)
''',
    '''def parse_problem(value):
    value = json.dumps({"questions": [value]})
    return json.loads(value)
''',
])
def test_plain_text_conversion_is_allowed_without_executing_source(source, parser):
    validate_binding(binding(parser) + '\nraise AssertionError("never import candidate")\n', configure(source))

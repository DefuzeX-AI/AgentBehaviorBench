"""Proven mapping-state/text mismatches fail even if a model approves them."""
from types import SimpleNamespace

import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.frameworks.langgraph.binding_validation import validate_binding
from agentbench.sdk.plugin.kuma.plugin import plugin
from tests.agent_build_fixtures import source, MANIFEST, FILES


def configure(source, *, input_key=False):
    (source.directory / 'agent/src/pkg/graph.py').write_text('''from langgraph.graph import StateGraph as Builder
from pkg.state import State
def build_graph():
    raise AssertionError("source must never be executed")
    return Builder(State).compile()
''', encoding='utf-8')
    (source.directory / 'agent/src/pkg/state.py').write_text('''from typing_extensions import TypedDict as Fields
class State(Fields):
    message: str
''', encoding='utf-8')
    manifest = MANIFEST if input_key else MANIFEST.replace('input_key = "message"\n', '')
    return SimpleNamespace(source=source, sdk=plugin, completed={'agent.toml': manifest},
                           current_path='bindings/bridge.py')


@pytest.mark.parametrize('binding', [
    'from pkg.graph import build_graph as native\ndef create_graph():\n return native()\n',
    'def create_graph():\n from pkg.graph import build_graph\n return build_graph()\n',
])
def test_text_cannot_be_forwarded_to_mapping_state(source, binding):
    session = configure(source)
    with pytest.raises(BuildError, match='worker does not run the upstream CLI'):
        validate_binding(binding, session)


def test_native_text_wrapper_and_input_key_remain_supported(source):
    session = configure(source)
    wrapper = '''class Wrapper:
    def invoke(self, value, config=None):
        import json
        from pkg.graph import build_graph
        state = {"message": value}
        return build_graph().invoke(state, config=config)
def create_graph():
    return Wrapper()
'''
    validate_binding(wrapper, session)
    session = configure(source, input_key=True)
    validate_binding('from pkg.graph import build_graph\ndef create_graph():\n return build_graph()\n', session)


def test_scalar_state_is_not_rejected_as_mapping(source):
    session = configure(source)
    (source.directory / 'agent/src/pkg/graph.py').write_text('''from langgraph.graph import StateGraph
def build_graph():
    return StateGraph(str).compile()
''', encoding='utf-8')
    validate_binding('from pkg.graph import build_graph\ndef create_graph():\n return build_graph()\n', session)

"""Source-confirmed runtime paths and conditional decisions cannot be disabled."""
import ast
from dataclasses import replace
from types import SimpleNamespace

import pytest

from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.frameworks.langgraph.native_initialization import validate_native_initialization
from tests.agent_build_fixtures import source


def session_for(source):
    (source.directory / 'agent/application.py').write_text('''from pkg.state import Review
def run(out, approve=False):
    initial = {"output_dir": str(out),
               "decision": Review(approved=True, notes="explicit option") if approve else None}
''', encoding='utf-8')
    return SimpleNamespace(source=replace(source, files=discover_files(source.directory / 'agent')))


@pytest.mark.parametrize('initial', [
    'def initial():\n return {"output_dir": None}\ninitial()\n',
    'def initial(output_dir=None):\n return {"output_dir": output_dir}\ninitial()\n',
])
def test_empty_runtime_directory_is_rejected(source, initial):
    with pytest.raises(BuildError, match='container-writable run directory'):
        validate_native_initialization(ast.parse(initial), session_for(source))


def test_unconditional_approval_is_rejected_despite_different_notes(source):
    code = 'from pkg.state import Review\ninitial={"decision":Review(approved=True,notes="benchmark")}'
    with pytest.raises(BuildError, match='never auto-approve'):
        validate_native_initialization(ast.parse(code), session_for(source))


def test_explicit_option_and_supplied_runtime_directory_are_allowed(source):
    code = '''from pkg.state import Review
def initial(output_dir=None, approve=False):
    return {"output_dir": output_dir,
            "decision": Review(approved=True, notes="explicit option") if approve else None}
initial("/tmp/run")
'''
    validate_native_initialization(ast.parse(code), session_for(source))

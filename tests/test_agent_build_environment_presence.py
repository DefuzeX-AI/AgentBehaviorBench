"""Default endpoint decisions use explicit host facts without disclosing values."""
from agentbench.onboarding.build_agent_env.openrouter_provider.context import environment_presence


def test_referenced_environment_presence_exposes_only_flags():
    context = {'files': [{'path': 'worker.py', 'content': '''import os
base = os.getenv("OPENAI_API_BASE")
key = os.environ.get("OPENAI_API_KEY")
unused = "SECRET_VALUE_SHOULD_NOT_BE_TRANSMITTED"
'''}]}
    result = environment_presence(context, {'OPENAI_API_KEY': 'SECRET_VALUE_SHOULD_NOT_BE_TRANSMITTED', 'UNRELATED_KEY': 'private'})
    assert result == {'OPENAI_API_BASE': False, 'OPENAI_API_KEY': True}
    assert all(type(value) is bool for value in result.values())


def test_truncated_python_is_not_executed_or_guessed():
    context = {'files': [{'path': 'worker.py', 'content': 'raise AssertionError("never run")\nos.getenv('}]}
    assert environment_presence(context, {}) == {}

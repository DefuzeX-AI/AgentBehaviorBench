"""Issue #54: credential fields are recognized however they are spelled, and only credential fields."""
import pytest

from agentbench.observe.store import REDACTED, TraceStore, environment_secrets, is_secret_field, redact

# The 15 spellings measured in the issue: 4 were masked, 11 passed through.
CREDENTIAL_FIELDS = ['api_key', 'authorization', 'password', 'access_token', 'token', 'apiKey', 'api-key',
                     'x-api-key', 'credential', 'credentials', 'bearer', 'private_key', 'refresh_token',
                     'session_token', 'passwd']
# Counts, provenance and names that sit next to credentials in real traces and configs.
ORDINARY_FIELDS = ['max_tokens', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'token_type',
                   'api_key_source', 'secret_env_keys', 'input_key', 'output_key', 'idempotency_key',
                   'tokenizer', 'keyring_backend']


@pytest.mark.parametrize('field', CREDENTIAL_FIELDS)
def test_every_measured_spelling_is_masked(field):
    assert redact({field: 'sk-live-value-1234567890'}) == {field: REDACTED}


@pytest.mark.parametrize('field', ORDINARY_FIELDS)
def test_ordinary_fields_near_credentials_stay_readable(field):
    assert redact({field: 'visible'}) == {field: 'visible'}


def test_llm_usage_counts_survive_redaction():
    payload = {'usage': {'prompt_tokens': 12, 'completion_tokens': 30, 'total_tokens': 42},
               'headers': {'Authorization': 'Bearer abc', 'X-Api-Key': 'abc'}}
    assert redact(payload) == {'usage': {'prompt_tokens': 12, 'completion_tokens': 30, 'total_tokens': 42},
                               'headers': {'Authorization': REDACTED, 'X-Api-Key': REDACTED}}


@pytest.mark.parametrize('field', ['secret_value', 'api_key_value', 'password_hash', 'clientSecret'])
def test_credential_values_under_suffixed_names_are_masked(field):
    assert is_secret_field(field)


def test_every_harvesting_site_uses_the_one_rule(tmp_path):
    from agentbench.cli.result_export import _environment_secrets
    from agentbench.harness.session.plan import environment_secrets as plan_secrets
    from agentbench.sdk.common.artifacts import Artifacts
    environ = {'DEFUZEX_API_KEY': 'dfx_abcdefghijklmnopqrstuvwxyz', 'GOG_KEYRING_BACKEND': 'file',
               'MAX_TOKENS': '4096', 'OPENROUTER_MODEL': 'deepseek-chat'}
    expected = ('dfx_abcdefghijklmnopqrstuvwxyz',)
    assert environment_secrets(environ) == expected
    assert _environment_secrets(environ) == expected
    assert plan_secrets(environ) == expected
    assert Artifacts(tmp_path, environ=environ).secrets == expected
    assert TraceStore(tmp_path / 'trace.jsonl', 'run', environ=environ)._secrets == expected

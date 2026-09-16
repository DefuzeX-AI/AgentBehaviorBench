"""Issue #59: harvesting environment secrets must not rewrite ordinary words in diagnostics."""
import json

from agentbench.observe.store import REDACTED, TraceStore, environment_secrets, redact
from agentbench.sdk.common.artifacts import Artifacts

TRACEBACK = ("    settings = json.loads(args.settings.read_text()) if args.settings.is_file() else {}\n"
             "PermissionError: [Errno 13] Permission denied: '/run/abb-input/evaluation.json'\n")


def test_selector_values_named_like_credentials_are_not_harvested():
    environ = {'GOG_KEYRING_BACKEND': 'file', 'TOKENIZERS_PARALLELISM': 'false', 'MAX_TOKENS': '4096',
               'USE_KEYCHAIN': 'yes', 'GOG_KEYRING_PASSWORD': ''}
    assert environment_secrets(environ) == ()


def test_the_traceback_that_explained_a_failure_survives(tmp_path):
    environ = {'GOG_KEYRING_BACKEND': 'file', 'DEFUZEX_API_KEY': 'dfx_abcdefghijklmnopqrstuvwxyz'}
    Artifacts(tmp_path, environ=environ).save('diagnostics.json', {'stderr': TRACEBACK})
    assert json.loads((tmp_path / 'diagnostics.json').read_text())['stderr'] == TRACEBACK
    TraceStore(tmp_path / 'network.jsonl', 'run', environ=environ).record('llm_response', text='the Excel file')
    assert json.loads((tmp_path / 'network.jsonl').read_text())['data']['text'] == 'the Excel file'


def test_long_credentials_are_still_masked_wherever_they_appear():
    secret = 'sk-945abcdefghijklmnop'
    text = f'Bearer {secret}; url=https://host/v1?key={secret}&x=1; glued=prefix{secret}suffix'
    assert secret not in redact(text, (secret,))
    assert redact(text, (secret,)).count(REDACTED) == 3


def test_short_harvested_values_are_masked_only_as_whole_tokens():
    secret = 'hunter2pw'  # long enough to harvest, short enough to collide with identifiers
    assert redact(f'password is {secret}.', (secret,)) == f'password is {REDACTED}.'
    assert redact(f'call my_{secret}_helper()', (secret,)) == f'call my_{secret}_helper()'


def test_provenance_of_the_credential_stays_readable():
    process = {'sdk': 'kuma', 'api_key_source': 'DEFUZEX_API_KEY', 'api_key': 'dfx_abcdefghijklmnopqrstuvwxyz'}
    assert redact(process, ('dfx_abcdefghijklmnopqrstuvwxyz',)) == {
        'sdk': 'kuma', 'api_key_source': 'DEFUZEX_API_KEY', 'api_key': REDACTED}

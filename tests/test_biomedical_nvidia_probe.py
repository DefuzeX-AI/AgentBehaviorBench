import io
import json
import urllib.error

from scripts.check_biomedical_nvidia import check


def respond(monkeypatch, body):
    class Response(io.BytesIO):
        status = 200
    monkeypatch.setattr('urllib.request.urlopen',
                        lambda *args, **kwargs: Response(json.dumps(body).encode()))


def test_embedding_checks_actual_vector(monkeypatch):
    respond(monkeypatch, {'data': [{'embedding': [0.1, 0.2]}]})
    result = check('embedding', 'https://example.test', {}, 'synthetic-secret', 1)
    assert result['inference_verified'] is True
    assert result['dimensions'] == 2
    respond(monkeypatch, {'data': []})
    assert not check('embedding', 'https://example.test', {}, 'synthetic-secret', 1)['inference_verified']


def test_molmim_checks_native_response(monkeypatch):
    respond(monkeypatch, {'molecules': json.dumps([{'sample': 'CCO'}])})
    result = check('molmim', 'https://example.test', {}, 'synthetic-secret', 1)
    assert result['upstream_response_compatible'] is True
    assert result['molecule_count'] == 1
    respond(monkeypatch, {'generated': [{'smiles': 'CCO'}]})
    assert not check('molmim', 'https://example.test', {}, 'synthetic-secret', 1)['upstream_response_compatible']


def test_errors_do_not_expose_secret(monkeypatch):
    def fail(*args, **kwargs):
        raise urllib.error.URLError('synthetic-secret')
    monkeypatch.setattr('urllib.request.urlopen', fail)
    result = check('embedding', 'https://example.test', {}, 'synthetic-secret', 1)
    assert result['error_type'] == 'URLError'
    assert 'synthetic-secret' not in json.dumps(result)

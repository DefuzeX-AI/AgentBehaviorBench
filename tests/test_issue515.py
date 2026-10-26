"""Octomind's outer integration preserves native behavior and shared routing."""
from pathlib import Path
import importlib.util
import json
import tomllib
import os
import copy
import shutil
import hashlib

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNIT = Path(os.environ.get('ABB_ISSUE515_UNIT', ROOT / 'resources/agents/127-octomind'))


@pytest.fixture
def launcher(tmp_path):
    spec = importlib.util.spec_from_file_location('issue515_launch', UNIT / 'bootstrap/launch.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cache = tmp_path / "bundled-models"
    (cache / "models--fixture--encoder/refs").mkdir(parents=True)
    (cache / "models--fixture--encoder/refs/main").write_text("pinned-revision")
    (cache / "model.onnx").write_bytes(b"public-model-fixture")
    module.DEFAULT_MODEL_CACHE = cache
    return module


@pytest.fixture
def setup(tmp_path):
    unit = tmp_path / 'unit'
    template = unit / 'agent/config-templates/default.toml'
    template.parent.mkdir(parents=True)
    template.write_text('[model]\nname="octohub:auto"\n[supervisor]\nenabled=true\n[supervisor.model]\nname="octohub:auto"\n[compression.model]\nname="octohub:auto"\n')
    shutil.copytree(ROOT / 'resources/agents/127-octomind/bootstrap/defaults', unit / 'bootstrap/defaults')
    tap = tmp_path / 'tap'
    tap.mkdir()
    return unit, tap, template


def environment():
    return {'ABB_AGENT_MODEL_API_KEY': 'fixture-not-a-real-key',
            'ABB_AGENT_MODEL_BASE_URL': 'https://model.invalid/v1/',
            'ABB_AGENT_MODEL': 'glm-5.3-flash', 'OPENAI_API_KEY': 'other-fixture',
            'OCTOHUB_API_KEY': 'other-fixture'}


def test_models_and_native_template(launcher, setup, tmp_path):
    unit, tap, template = setup
    before = template.read_bytes()
    cmd, env = launcher.prepare(environment(), tmp_path / 'home', unit=unit, tap=tap)
    config = Path(env['OCTOMIND_CONFIG_PATH'])
    overlay = tomllib.loads((config.parent / 'zz-abb-model.toml').read_text())
    assert config.read_bytes() == before == template.read_bytes()
    assert overlay['model']['name'] == overlay['supervisor']['model']['name'] == overlay['compression']['model']['name'] == 'openrouter:glm-5.3-flash'
    assert set(overlay) == {'model', 'supervisor', 'compression'}
    assert cmd == ['/usr/local/bin/octomind', 'acp', 'developer:general', '--model', 'openrouter:glm-5.3-flash']
    assert env['OPENROUTER_API_URL'] == 'https://model.invalid/v1/chat/completions'
    assert env['OPENROUTER_API_KEY'] == environment()['ABB_AGENT_MODEL_API_KEY']
    assert 'OPENAI_API_KEY' not in env and 'OCTOHUB_API_KEY' not in env
    assert 'fixture-not-a-real-key' not in ''.join(p.read_text() for p in config.parent.iterdir())
    assert (Path(env['OCTOMIND_DATA_DIR']) / 'taps/muvon/octomind-tap').resolve() == tap


@pytest.mark.parametrize('name', ['ABB_AGENT_MODEL_API_KEY', 'ABB_AGENT_MODEL_BASE_URL', 'ABB_AGENT_MODEL'])
def test_missing_fields_fail_before_native_start(launcher, setup, tmp_path, name):
    unit, tap, _ = setup
    env = environment()
    del env[name]
    with pytest.raises(ValueError, match=name):
        launcher.prepare(env, tmp_path / 'home', unit=unit, tap=tap)


@pytest.mark.parametrize('base', ['http://model.invalid/v1', 'https://user:pass@model.invalid/v1',
                                  'https://model.invalid/v1?key=fixture', 'https://model.invalid/v1#frag'])
def test_invalid_base_is_rejected(launcher, setup, tmp_path, base):
    unit, tap, _ = setup
    env = environment()
    env['ABB_AGENT_MODEL_BASE_URL'] = base
    with pytest.raises(ValueError, match='HTTPS base URL'):
        launcher.prepare(env, tmp_path / 'home', unit=unit, tap=tap)


def test_source_and_release_share_commit():
    manifest = tomllib.loads((UNIT / 'agent.toml').read_text())
    provenance = json.loads((UNIT / 'source-provenance.json').read_text())
    assert manifest['source']['method'] == 'git'
    assert manifest['source']['revision'] == provenance['revision'] == 'aa08782640ddc441e8a0ef0f1bf25bec85344a73'
    assert provenance['native_files_modified'] is False
    assert manifest.get('model') == {'metadata_paths': ['/models']}
    assert 'provider' not in manifest['model']
    assert manifest['adapter']['permission_policy'] == 'allow_once'
    assert not manifest['llm_interception'].get('routes')


def test_published_release_hash_pins():
    release = json.loads((UNIT / 'bootstrap/distributions.json').read_text())
    assert set(release['architectures']) == {'amd64', 'arm64'}
    for arch, digest in [('amd64', 'cb0e7ca22b050b54ace06393b25523fb0ace532673e7ba928365940ab8895b75'),
                         ('arm64', '72fdf4681ecab1f986553bb3fbf0ff4e48d683bc7157e4ec39f10e4a6ca2ebc8')]:
        records = release['architectures'][arch]
        assert {r['binary'] for r in records} == {'octomind', 'octofs', 'octocode', 'octobrain'}
        assert all(r['url'].startswith('https://github.com/Muvon/') and len(r['sha256']) == 64 for r in records)
        assert next(r for r in records if r['binary'] == 'octomind')['sha256'] == digest
    node = json.loads((UNIT / 'bootstrap/node.json').read_text())
    assert node['version'] == '22.23.4'
    assert node['checksum_source'] == 'https://nodejs.org/dist/v22.23.4/SHASUMS256.txt'
    assert node['architectures']['amd64']['sha256'] == '1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce'
    assert node['architectures']['arm64']['sha256'] == '6287aa46b6c375d816e63ae66d024fbbfd70404825aabdfdf898a970871d2f4b'


def test_native_architecture_not_forced_to_emulation():
    dockerfile = (UNIT / 'Dockerfile').read_text()
    assert 'FROM --platform=linux/amd64' not in dockerfile
    spec = importlib.util.spec_from_file_location('issue515_installer', UNIT / 'bootstrap/install_releases.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.architecture('aarch64') == 'arm64'
    assert module.architecture('x86_64') == 'amd64'
    with pytest.raises(ValueError, match='Unsupported'):
        module.architecture('riscv64')


def test_every_sidecar_text_model_is_routed_and_other_settings_unchanged(launcher, setup, tmp_path):
    unit, tap, _ = setup
    _, env = launcher.prepare(environment(), tmp_path / 'home', unit=unit, tap=tap)
    original = tomllib.loads((unit / 'bootstrap/defaults/octocode.toml').read_text())
    expected = copy.deepcopy(original)
    for section, fields in launcher.TEXT_MODEL_FIELDS.items():
        table = expected
        for part in section.split('.'):
            table = table[part]
        for field in fields:
            table[field] = 'openrouter:glm-5.3-flash'
    overrides = json.loads((ROOT / 'resources/agents/127-octomind/bootstrap/local-models.json').read_text())['native_config']
    for section, fields in overrides['octocode'].items():
        table = expected
        for part in section.split('.'):
            table = table[part]
        table.update(fields)
    actual = tomllib.loads(Path(env['OCTOCODE_CONFIG_PATH']).read_text())
    assert actual == expected
    assert len([(s, f) for s, fs in launcher.TEXT_MODEL_FIELDS.items() for f in fs]) == 5
    brain = tomllib.loads((unit / 'bootstrap/defaults/octobrain.toml').read_text())
    for section, fields in overrides['octobrain'].items():
        table = brain
        for part in section.split('.'):
            table = table[part]
        table.update(fields)
    assert tomllib.loads(Path(env['OCTOBRAIN_CONFIG_PATH']).read_text()) == brain
    assert actual['search']['reranker']['enabled'] is original['search']['reranker']['enabled'] is True
    assert actual['index']['mcp_index'] is False
    assert 'fixture-not-a-real-key' not in Path(env['OCTOCODE_CONFIG_PATH']).read_text()


def test_missing_native_llm_slot_fails_closed(launcher):
    original = (UNIT / 'bootstrap/defaults/octocode.toml').read_text()
    with pytest.raises(ValueError, match='all expected.*fields'):
        launcher.configure_octocode(original.replace('contextual_model =', '# contextual_model ='), 'openrouter:glm-5.3-flash')


def test_dependency_templates_match_recorded_original_hashes():
    defaults = UNIT / 'bootstrap/defaults'
    pins = json.loads((defaults / 'provenance.json').read_text())
    assert set(pins) == {'octocode', 'octobrain'}
    for name, record in pins.items():
        assert hashlib.sha256((defaults / (name + '.toml')).read_bytes()).hexdigest() == record['sha256']


def test_no_replacement_loop_or_native_tool_filter(launcher):
    source = (UNIT / 'bootstrap/launch.py').read_text()
    assert 'os.execvpe' in source
    assert 'allowed_tools' not in source
    assert 'supervisor.enabled' not in source
    import ast
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Import) and any(a.name=='subprocess' for a in n.names) for n in ast.walk(tree))
    assert 'OPENROUTER_API_URL' in source


def test_native_npx_keeps_original_command_and_private_preferred_cache(launcher, setup, tmp_path):
    unit, tap, _ = setup
    cache = tmp_path / 'npm-seed'
    (cache / '_cacache').mkdir(parents=True)
    (cache / '_cacache/pinned-package-metadata').write_text('public fixture')
    _, env = launcher.prepare(environment(), tmp_path / 'home', unit=unit, tap=tap, npm_cache=cache)
    private_cache = Path(env['npm_config_cache'])
    assert (private_cache / '_cacache/pinned-package-metadata').read_text() == 'public fixture'
    assert private_cache != cache
    assert env['npm_config_prefer_offline'] == 'true'
    assert 'npm_config_offline' not in env
    assert env['npm_config_update_notifier'] == 'false'
    assert 'cp -a /root/.npm/_cacache /opt/octomind-npm-cache/_cacache' in (UNIT / 'Dockerfile').read_text()
    assert 'npm exec --yes --package=open-websearch@2.2.0 -- node --version' in (UNIT / 'Dockerfile').read_text()
    assert 'cp -a /root/.npm/_npx /opt/octomind-npm-cache/_npx' in (UNIT / 'Dockerfile').read_text()
    (private_cache / '_cacache/pinned-package-metadata').write_text('changed private cache')
    assert (cache / '_cacache/pinned-package-metadata').read_text() == 'public fixture'



def test_model_cache_uses_links_but_isolates_writable_refs(launcher, setup, tmp_path):
    unit, tap, _ = setup
    _, env = launcher.prepare(environment(), tmp_path / 'home', unit=unit, tap=tap)
    cache = Path(env['XDG_CACHE_HOME']) / 'octolib/huggingface'
    assert (cache / 'model.onnx').is_symlink()
    assert (cache / 'model.onnx').read_bytes() == b'public-model-fixture'
    ref = cache / 'models--fixture--encoder/refs/main'
    assert not ref.is_symlink()
    ref.write_text('new-private-revision')
    assert (launcher.DEFAULT_MODEL_CACHE / 'models--fixture--encoder/refs/main').read_text() == 'pinned-revision'
    (cache / 'new-model').mkdir()
    assert not (launcher.DEFAULT_MODEL_CACHE / 'new-model').exists()


def test_seeded_npm_preserves_cache_miss_writes_without_copying_packages(launcher, tmp_path):
    source = tmp_path / 'seed'
    (source / '_npx/hash/node_modules').mkdir(parents=True)
    (source / '_npx/hash/node_modules/entry.js').write_text('public package')
    (source / '_cacache/content-v2/sha512').mkdir(parents=True)
    (source / '_cacache/content-v2/sha512/pinned').write_text('public archive')
    target = tmp_path / 'private'
    launcher.seed_cache(source, target)
    assert (target / '_npx/hash/node_modules').is_symlink()
    assert (target / '_cacache/content-v2/sha512/pinned').is_symlink()
    (target / '_cacache/content-v2/sha512/new').write_text('new cache miss')
    assert not (source / '_cacache/content-v2/sha512/new').exists()


def test_missing_packaged_models_fail_before_native_start(launcher, setup, tmp_path):
    unit, tap, _ = setup
    with pytest.raises(ValueError, match='Bundled public dependency cache'):
        launcher.prepare(environment(), tmp_path / 'home', unit=unit, tap=tap, model_cache=tmp_path / 'missing')


def asset_installer():
    spec = importlib.util.spec_from_file_location('issue515_models', UNIT / 'bootstrap/prefetch_models.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_asset_cache_is_rehashed_and_installed_without_network(tmp_path, monkeypatch):
    module = asset_installer()
    data = b'original public fixture'
    sha = hashlib.sha256(data).hexdigest()
    cache = tmp_path / 'cache';cache.mkdir();(cache / sha).write_bytes(data)
    item = {'repository': 'fixture/model', 'revision': 'a' * 40, 'path': 'onnx/model.onnx', 'bytes': len(data), 'sha256': sha}
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: pytest.fail('Verified cached asset must not download'))
    module.install({'assets': [item]}, cache, tmp_path / 'models')
    assert (tmp_path / 'models/models--fixture--model/snapshots' / ('a' * 40) / 'onnx/model.onnx').read_bytes() == data
    assert (tmp_path / 'models/models--fixture--model/refs/main').read_text() == 'a' * 40


def test_corrupted_model_asset_is_rejected(tmp_path, monkeypatch):
    module = asset_installer()
    cache = tmp_path / 'cache';cache.mkdir();(cache / ('0' * 64)).write_bytes(b'wrong')
    item = {'repository': 'fixture/model', 'revision': 'a' * 40, 'path': 'model.onnx', 'bytes': 5, 'sha256': '0' * 64}
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **k: None)
    with pytest.raises(ValueError, match='checksum mismatch'):
        module.install({'assets': [item]}, cache, tmp_path / 'models')


def test_public_asset_manifest_and_paths_are_pinned():
    module = asset_installer()
    manifest = json.loads((UNIT / 'bootstrap/local-models.json').read_text())
    assert sum(a['bytes'] for a in manifest['assets']) == 211110711
    assert {a['repository'] for a in manifest['assets']} == {'Xenova/all-MiniLM-L6-v2', 'jinaai/jina-reranker-v1-turbo-en', 'muvon/octomind-embed'}
    assert len(manifest['assets']) == 16
    for path in ['/etc/passwd', '../escape']:
        with pytest.raises(ValueError):
            module.safe_path(path)


def transport_module():
    spec = importlib.util.spec_from_file_location('issue515_transport', UNIT / 'bootstrap/model_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transport_accepts_only_selected_https_target():
    module = transport_module()
    assert module.verified_target({'ABB_AGENT_MODEL_BASE_URL': 'https://model.invalid/v1/'}) == 'https://model.invalid/v1'
    for base in ['http://model.invalid', 'https://u:p@model.invalid', 'https://model.invalid?k=v']:
        with pytest.raises(ValueError):
            module.verified_target({'ABB_AGENT_MODEL_BASE_URL': base})


@pytest.fixture
def tls_upstream(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import ssl, threading, subprocess
    openssl = shutil.which('openssl')
    if not openssl:
        pytest.skip('TLS transport fixture requires the host OpenSSL CLI')
    crt, pem = tmp_path / 'ca.pem', tmp_path / 'key.pem'
    config = tmp_path / 'openssl.cnf'
    config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n[dn]\nCN=localhost\n[v3]\nbasicConstraints=critical,CA:true\nsubjectAltName=DNS:localhost\n')
    subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-keyout', str(pem), '-out', str(crt), '-config', str(config)],
                   capture_output=True, check=True, timeout=20)
    seen = []
    class Echo(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('content-length', '0')))
            seen.append((self.path, raw, self.headers.get('Authorization')))
            self.send_response(429 if raw == b'error-fixture' else 200)
            self.send_header('Content-Type', 'text/event-stream');self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            seen.append((self.path, None, self.headers.get('Authorization')))
            self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[]}')
    server = ThreadingHTTPServer(('localhost', 0), Echo)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(crt, pem)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield 'https://localhost:' + str(server.server_address[1]), crt, seen
    server.shutdown();server.server_close()


def test_transport_preserves_request_sse_error_and_metadata_bytes(tls_upstream):
    from http.server import ThreadingHTTPServer
    import ssl, threading, urllib.request, urllib.error
    module = transport_module();base, crt, seen = tls_upstream
    server = ThreadingHTTPServer(('127.0.0.1', 0), module.handler(base, ssl.create_default_context(cafile=str(crt))))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = 'http://127.0.0.1:' + str(server.server_address[1])
    try:
        data = b'data: {"fixture":"wire bytes"}\n\ndata: [DONE]\n\n'
        req = urllib.request.Request(root + '/v1/chat/completions', data, {'Authorization': 'Bearer fixture-only'})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.read() == data and r.status == 200
        assert seen[-1] == ('/chat/completions', data, 'Bearer fixture-only')
        with urllib.request.urlopen(root + '/v1/models', timeout=5) as r: assert r.read() == b'{"data":[]}'
        with pytest.raises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(urllib.request.Request(root + '/v1/chat/completions', b'error-fixture'), timeout=5)
        assert result.value.code == 429 and result.value.read() == b'error-fixture'
        with pytest.raises(urllib.error.HTTPError) as result: urllib.request.urlopen(root + '/unconfigured', timeout=5)
        assert result.value.code == 404
    finally:
        server.shutdown();server.server_close()


def test_transport_rejects_untrusted_https_certificate(tls_upstream):
    from http.server import ThreadingHTTPServer
    import ssl, threading, urllib.request, urllib.error
    module = transport_module();base, _, seen = tls_upstream
    server = ThreadingHTTPServer(('127.0.0.1', 0), module.handler(base, ssl.create_default_context()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:' + str(server.server_address[1]) + '/v1/chat/completions', b'not-sent'), timeout=5)
        assert result.value.code == 502
        assert seen == []
    finally:
        server.shutdown();server.server_close()


def prefetch_module():
    spec = importlib.util.spec_from_file_location('issue515_prefetch', UNIT / 'bootstrap/prefetch_models.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_download_refreshes_redirect_without_changing_asset_identity(tmp_path, monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    module = prefetch_module()
    data = b'original-public-tensor-fixture'
    digest = hashlib.sha256(data).hexdigest()
    asset = {'repository': 'Example/public', 'revision': 'a' * 40,
             'path': 'onnx/model.onnx', 'bytes': len(data), 'sha256': digest}
    calls = []
    clock = iter([1001, 1002])
    monkeypatch.setattr(module.time, 'time_ns', lambda: next(clock))
    def download(argv, **kwargs):
        calls.append(argv)
        Path(argv[argv.index('-o') + 1]).write_bytes(data)
    monkeypatch.setattr(module.subprocess, 'run', download)
    for n in [1, 2]:
        module.install({'assets': [asset]}, tmp_path / str(n), tmp_path / ('dest' + str(n)))
    urls = [next(s for s in a if s.startswith('https://')) for a in calls]
    assert urls[0] != urls[1]
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.netloc == 'huggingface.co'
        assert parsed.path == '/Example/public/resolve/' + 'a' * 40 + '/onnx/model.onnx'
        assert parse_qs(parsed.query)['abb_sha256'] == [digest]
        assert parse_qs(parsed.query)['download'] == ['true']
    assert all('--fail' in a and '--continue-at' in a and '-k' not in a for a in calls)
    module.install({'assets': [asset]}, tmp_path / '1', tmp_path / 'cached-dest')
    assert len(calls) == 2


def test_public_download_hash_mismatch_still_fails_closed(tmp_path, monkeypatch):
    module = prefetch_module()
    asset = {'repository': 'Example/public', 'revision': 'b' * 40,
             'path': 'onnx/model.onnx', 'bytes': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
    def wrong_bytes(argv, **kwargs):
        Path(argv[argv.index('-o') + 1]).write_bytes(b'evil')
    monkeypatch.setattr(module.subprocess, 'run', wrong_bytes)
    with pytest.raises(ValueError, match='checksum mismatch'):
        module.install({'assets': [asset]}, tmp_path / 'cache', tmp_path / 'destination')
    assert not (tmp_path / 'destination/models--Example--public').exists()

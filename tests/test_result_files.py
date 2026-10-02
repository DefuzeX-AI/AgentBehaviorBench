"""Result browsing must remain bounded to a Suite-authorized artifact run."""
import json
from pathlib import Path
import subprocess
import sys
import pytest

from agentbench.observe.view_api import RunViewAPI
from agentbench.observe import result_files
from agentbench.observe.case_generation import generation


def save(root, name, value):
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def test_lazy_directory_and_original_unicode_preview(tmp_path):
    save(tmp_path, 'evaluation/case.json', {'prompt': '你好 🌿'})
    save(tmp_path, 'run.json', {'run_id': tmp_path.name})
    api = RunViewAPI(tmp_path)
    prefix = f'/api/observe/runs/{tmp_path.name}/'
    page = api.route(prefix + 'files', {})
    assert [entry['path'] for entry in page['entries']] == ['evaluation', 'run.json']
    assert page['entries'][0]['type'] == 'directory'
    child = api.route(prefix + 'files', {'path': ['evaluation']})
    assert child['entries'][0]['path'] == 'evaluation/case.json'
    viewed = api.route(prefix + 'file', {'path': ['evaluation/case.json']})
    assert viewed['text'] == (tmp_path / 'evaluation/case.json').read_text(encoding='utf-8')
    assert viewed['binary'] is False and viewed['truncated'] is False


@pytest.mark.parametrize('relative', ['../outside', 'evaluation/../../outside', '/outside',
                                     'C:/outside', 'evaluation\\case.json', './run.json', 'evaluation//case.json'])
def test_paths_cannot_escape_or_use_windows_aliases(tmp_path, relative):
    with pytest.raises((ValueError, OSError)):
        result_files.preview_file(tmp_path, relative)


def test_symlink_files_and_directory_links_are_not_followed(tmp_path):
    root = tmp_path / 'result'
    root.mkdir()
    save(tmp_path, 'outside/secret.json', {'secret': 'do not read'})
    try:
        (root / 'linked').symlink_to(tmp_path / 'outside', target_is_directory=True)
        (root / 'secret.json').symlink_to(tmp_path / 'outside/secret.json')
    except OSError:
        pytest.skip('Creating symlinks requires permission on this host')
    assert result_files.list_files(root)['entries'] == []
    for relative in ('linked/secret.json', 'secret.json'):
        with pytest.raises(ValueError):
            result_files.preview_file(root, relative)


def test_windows_junction_is_excluded(tmp_path):
    if sys.platform != 'win32':
        pytest.skip('Windows junction')
    root, outside = tmp_path / 'result', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    save(outside, 'secret.json', {'secret': 'do not read'})
    linked = root / 'linked'
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(outside)], check=True, capture_output=True)
    try:
        assert result_files.list_files(root)['entries'] == []
        with pytest.raises(ValueError):
            result_files.preview_file(root, 'linked/secret.json')
    finally:
        linked.rmdir()  # Remove only the junction itself, never its target.


def test_pagination_binary_and_truncated_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(result_files, 'PAGE_SIZE', 2)
    for name in ('b.txt', 'a.txt', 'c.txt'):
        (tmp_path / name).write_text('ok')
    page = result_files.list_files(tmp_path)
    assert [entry['name'] for entry in page['entries']] == ['a.txt', 'b.txt']
    assert page['next'] == 2
    assert result_files.list_files(tmp_path, offset=2)['next'] is None
    monkeypatch.setattr(result_files, 'PREVIEW_BYTES', 4)
    (tmp_path / 'unicode.txt').write_bytes('ab你好'.encode('utf8'))
    preview = result_files.preview_file(tmp_path, 'unicode.txt')
    assert preview['text'] == 'ab' and preview['truncated']
    assert preview['size'] == 8
    (tmp_path / 'binary.bin').write_bytes(b'\x00\xff')
    assert result_files.preview_file(tmp_path, 'binary.bin')['binary']
    with pytest.raises(ValueError):
        result_files.list_files(tmp_path, offset=-1)


def test_generation_reads_saved_exports_without_sdk_and_preserves_failures(tmp_path):
    save(tmp_path, 'run.json', {'run_id': tmp_path.name, 'status': 'failed'})
    artifact = {'schema_version': 'kuma.case_artifact.v1', 'case': {'case_id': 'case-a', 'steps': ['你好']}}
    save(tmp_path, 'evaluation/cases/abb-case-0001.json', artifact)
    save(tmp_path, 'evaluation/case-collection.json', {'cases': [
        {'case_index': 0, 'case_id': 'case-a', 'artifact': '.kuma/abb-case-0001.json'},
        {'case_index': 2, 'case_id': 'case-c', 'artifact': '.kuma/abb-case-0003.json'}],
        'failures': [{'case_index': 1, 'code': 'quota_exhausted'}]})
    save(tmp_path, 'evaluation/case-generation-profile.json', {'content': 'original profile'})
    value = generation(tmp_path)
    assert value['cases'][0]['artifact'] == artifact
    assert value['cases'][1]['artifact'] is None
    assert value['collection']['failures'][0]['code'] == 'quota_exhausted'
    assert value['profile']['content'] == 'original profile'
    assert RunViewAPI(tmp_path).route(f'/api/observe/runs/{tmp_path.name}/generation', {}) == value


def test_generation_missing_and_unsafe_artifact_references(tmp_path):
    assert generation(tmp_path)['cases'] == []
    save(tmp_path, 'evaluation/case-collection.json', {'cases': [
        {'case_index': 0, 'artifact': '../../secret.json'},
        {'case_index': 1, 'artifact': '.kuma/../secret.json'}]})
    assert all(case['artifact'] is None for case in generation(tmp_path)['cases'])

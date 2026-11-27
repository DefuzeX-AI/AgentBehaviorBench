"""Preserve large native responses without weakening the controller boundary."""
import hashlib
import os
from pathlib import Path

import pytest


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


@pytest.mark.skipif(os.name == 'nt', reason='Descriptor-relative transport runs in Linux containers')
def test_native_trace_larger_than_legacy_budget_is_copied_completely(tmp_path):
    from agentbench.sdk.integration.channel import collect_response
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    trace = source / 'framework.jsonl'
    # A sparse source keeps the test inexpensive while exercising real I/O past
    # the former 128 MiB cap. The last byte must survive, not just a prefix.
    with trace.open('wb') as stream:
        stream.seek(129 * 1024 * 1024)
        stream.write(b'last byte\n')
    (source / 'result.json').write_text('{"status":"succeeded"}')
    (source / 'done.json').write_text('{"sequence":0}')
    collect_response(source, target)
    assert (target / trace.name).stat().st_size == trace.stat().st_size
    assert digest(target / trace.name) == digest(trace)
    assert (target / 'result.json').read_bytes() == (source / 'result.json').read_bytes()
    assert not (target / 'done.json').exists()


def test_response_budget_defaults_and_explicit_configuration():
    from agentbench.sdk.integration.context import ResponseLimits
    assert ResponseLimits.from_environ({}) == ResponseLimits(1024 ** 3, 20000)
    assert ResponseLimits.from_environ({
        'ABB_AGENT_RESPONSE_MAX_BYTES': '536870912',
        'ABB_AGENT_RESPONSE_MAX_FILES': '25000',
    }) == ResponseLimits(536870912, 25000)


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'unlimited', ''])
def test_invalid_response_budget_is_rejected(value):
    from agentbench.sdk.integration.context import ResponseLimits
    with pytest.raises(ValueError, match='ABB_AGENT_RESPONSE_MAX_BYTES'):
        ResponseLimits.from_environ({'ABB_AGENT_RESPONSE_MAX_BYTES': value})


def test_small_explicit_budget_fails_without_publishing_a_truncated_file(tmp_path):
    from agentbench.sdk.integration.channel import collect_response
    from agentbench.sdk.integration.context import ResponseLimits
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    (source / 'framework.jsonl').write_bytes(b'full original evidence')
    with pytest.raises(ValueError, match='transport byte limit.*framework.jsonl'):
        collect_response(source, target, limits=ResponseLimits(max_bytes=8))
    assert not (target / 'framework.jsonl').exists()
    assert (source / 'framework.jsonl').read_bytes() == b'full original evidence'


def test_response_budget_counts_all_files_in_nested_directories(tmp_path):
    from agentbench.sdk.integration.channel import collect_response
    from agentbench.sdk.integration.context import ResponseLimits
    source, target = tmp_path / 'source', tmp_path / 'target'
    (source / 'otel-payloads').mkdir(parents=True)
    target.mkdir()
    (source / 'framework.jsonl').write_bytes(b'abcd')
    (source / 'otel-payloads' / 'span.json').write_bytes(b'efgh')
    collect_response(source, target, limits=ResponseLimits(max_bytes=8))
    assert (target / 'otel-payloads' / 'span.json').read_bytes() == b'efgh'
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(ValueError, match='transport byte limit'):
        collect_response(source, other, limits=ResponseLimits(max_bytes=7))


@pytest.mark.skipif(os.name == 'nt', reason='Descriptor-relative transport runs in Linux containers')
def test_response_growing_during_copy_does_not_publish_a_partial_file(tmp_path, monkeypatch):
    from agentbench.sdk.integration.channel import collect_response
    from agentbench.sdk.integration.context import ResponseLimits
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    path = source / 'framework.jsonl'
    path.write_bytes(b'ab')
    original_read = os.read
    grew = False

    def read_and_grow(fd, size):
        nonlocal grew
        block = original_read(fd, size)
        if not grew:
            with path.open('ab') as stream:
                stream.write(b'cd')
            grew = True
        return block

    monkeypatch.setattr(os, 'read', read_and_grow)
    with pytest.raises(ValueError, match='transport byte limit'):
        collect_response(source, target, limits=ResponseLimits(max_bytes=3))
    assert list(target.iterdir()) == []
    assert path.read_bytes() == b'abcd'


@pytest.mark.skipif(os.name == 'nt', reason='Descriptor-relative transport runs in Linux containers')
@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'file_count'])
def test_larger_byte_budget_preserves_link_special_file_and_count_guards(tmp_path, kind):
    from agentbench.sdk.integration.channel import collect_response
    from agentbench.sdk.integration.context import ResponseLimits
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.mkdir()
    target.mkdir()
    if kind == 'symlink':
        private = tmp_path / 'private'
        private.write_text('must not be read')
        (source / 'result.json').symlink_to(private)
        error = OSError
    elif kind == 'fifo':
        os.mkfifo(source / 'result.json')
        error = ValueError
    else:
        (source / 'one.json').write_text('{}')
        (source / 'two.json').write_text('{}')
        error = ValueError
    with pytest.raises(error):
        collect_response(source, target, limits=ResponseLimits(max_files=1))

import hashlib
from pathlib import Path
import zipfile

import pytest

from scripts.inspect_biomedical_data import inspect_archive


def inspect_fixture(path):
    return inspect_archive(path, expected_size=path.stat().st_size,
                           expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_valid_archive_is_only_inspected(tmp_path):
    path = tmp_path / 'data.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('collection/paper.pdf', b'%PDF-1.4\n')
    result = inspect_fixture(path)
    assert result['pdf_count'] == 1
    assert result['sha256_verified'] is True
    assert not (tmp_path / 'collection').exists()


@pytest.mark.parametrize('member', ['../paper.pdf', '/paper.pdf', 'C:/paper.pdf', 'a\\paper.pdf'])
def test_unsafe_members_rejected(tmp_path, member):
    path = tmp_path / 'data.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(member, b'%PDF-1.4\n')
    with pytest.raises(ValueError, match='Unsafe archive'):
        inspect_fixture(path)


def test_lfs_pointer_is_not_accepted_as_data(tmp_path):
    path = tmp_path / 'data.zip'
    path.write_text('version https://git-lfs.github.com/spec/v1\n')
    with pytest.raises(ValueError, match='size'):
        inspect_archive(path)


def test_hash_mismatch_rejected(tmp_path):
    path = tmp_path / 'data.zip'
    path.write_bytes(b'wrong data')
    with pytest.raises(ValueError, match='SHA256'):
        inspect_archive(path, expected_size=path.stat().st_size, expected_sha256='wrong')

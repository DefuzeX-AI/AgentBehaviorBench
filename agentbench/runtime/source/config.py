"""Explicit opt-in to Git acquisition; existing units remain bundled."""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class GitSource:
    repository: str
    revision: str


@dataclass(frozen=True)
class InstallSource:
    """Checked-in installation inputs, materialized into agent/ before SDK use."""
    directory: str = 'install'


def source_spec(manifest):
    source = manifest.get('source', {})
    if not isinstance(source, dict):
        raise ValueError('source must be a table')
    method = source.get('method', 'bundled')
    if method == 'bundled':
        return None
    if method not in {'git', 'install'}:
        raise ValueError('source.method must be bundled, git or install')
    if manifest.get('runtime', {}).get('type') != 'docker':
        raise ValueError('Source preparation currently requires Docker runtime')
    if method == 'install':
        return InstallSource()
    return git_source_spec(source.get('repository', ''), source.get('revision', ''))


def git_source_spec(repository, revision):
    """Validate a pinned Git source independently of runtime preparation."""
    if not isinstance(repository, str):
        raise ValueError('source.repository must be an HTTPS repository URL')
    url = urlsplit(repository)
    if (url.scheme != 'https' or not url.hostname or not url.path.strip('/')
            or url.username or url.password or url.query or url.fragment):
        raise ValueError('source.repository must be an HTTPS repository URL without credentials')
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', revision):
        raise ValueError('source.revision must be a full 40-character commit SHA')
    return GitSource(repository, revision.lower())

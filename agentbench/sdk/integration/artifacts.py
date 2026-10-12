"""Filesystem implementation rooted in the existing Suite result directory."""
import hashlib
import json
import re
import threading
from pathlib import Path

from agentbench.harness.session.atomic import atomic_bytes
from agentbench.sdk.common.artifacts import Artifacts


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise ValueError('Invalid artifact identifier')
    return value


def child(root, relative):
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in ('.', '..') for p in path.parts):
        raise ValueError('Artifact path must be a relative descendant')
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()) or any(
            p.is_symlink() for p in (target, *target.parents) if p != root.parent):
        raise ValueError('Artifact paths cannot follow links')
    return target


class FileAttemptArtifacts:
    def __init__(self, directory, environ=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.files = Artifacts(self.directory, environ=environ)
        self.lock = threading.Lock()

    def write_json(self, relative, value):
        child(self.directory, relative)
        self.files.save(relative, value)

    def append_event(self, value):
        from agentbench.observe.store import redact, json_value
        path = child(self.directory, 'events.jsonl')
        with self.lock, path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(redact(json_value(value), self.files.secrets), ensure_ascii=False) + '\n')
            stream.flush()

    def private_directory(self, name):
        path = child(self.directory, 'sdk/' + component(name))
        path.mkdir(parents=True, exist_ok=True)
        return path


class FileCaseArtifacts:
    def __init__(self, directory, environ=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.environ = environ

    def publish_case(self, content):
        path = child(self.directory, 'case.json')
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError('A published Case cannot be replaced')
        else:
            atomic_bytes(path, content)
        return path

    def attempt(self, identifier):
        return FileAttemptArtifacts(child(self.directory, 'attempts/' + component(identifier)), self.environ)


class FileArtifactStore:
    def __init__(self, directory, *, environ=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.environ = environ

    def case(self, agent_id, case_index):
        if not isinstance(agent_id, str) or not agent_id or type(case_index) is not int or case_index < 0:
            raise ValueError('Case storage requires an Agent identity and nonnegative slot')
        key = hashlib.sha256(agent_id.encode()).hexdigest()[:24]
        return FileCaseArtifacts(child(self.directory, f'cases/{key}/{case_index}'), self.environ)

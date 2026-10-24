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
        return FileAttemptArtifacts(child(self.directory, 'trajectory/' + component(identifier)), self.environ)


class FileArtifactStore:
    def __init__(self, directory, *, environ=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.environ = environ
        plan = self.directory / 'plan.json'
        self.managed = (plan.is_file() and json.loads(plan.read_text(encoding='utf-8')).get(
            'artifact_layout') == 'agent-trajectories-v1')

    def agent_directory(self, agent_id):
        component(agent_id)
        root = self.directory.parent.parent if self.directory.parent.name == 'suites' else self.directory.parent
        path = child(root, 'agents/' + agent_id)
        path.mkdir(parents=True, exist_ok=True)
        identity = path / 'agent.json'
        if not identity.exists():
            from agentbench.harness.session.atomic import atomic_json
            atomic_json(identity, {'agent_id': agent_id})
        return path

    def preparation(self, agent_id):
        from uuid import uuid4
        root = self.agent_directory(agent_id) if self.managed else self.directory
        path = child(root, ('preparations/' if self.managed else 'preparation/') + uuid4().hex)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        path.mkdir()
        return path

    def case(self, agent_id, case_index):
        if not isinstance(agent_id, str) or not agent_id or type(case_index) is not int or case_index < 0:
            raise ValueError('Case storage requires an Agent identity and nonnegative slot')
        key = hashlib.sha256(agent_id.encode()).hexdigest()[:8]
        if self.managed:
            # A slot is allocated before an SDK has generated its Case ID. Scope
            # its stable storage identity to the Suite so different runs cannot alias.
            from uuid import uuid5, NAMESPACE_URL
            slot = uuid5(NAMESPACE_URL, f'{self.directory.as_posix()}:{agent_id}:{case_index}').hex
            return FileCaseArtifacts(child(self.agent_directory(agent_id), f'cases/{slot}'), self.environ)
        return FileCaseArtifacts(child(self.directory, f'cases/{key}/{case_index}'), self.environ)

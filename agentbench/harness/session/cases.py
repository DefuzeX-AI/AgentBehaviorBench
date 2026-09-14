"""Retain immutable prepared Case bytes independently of temporary Run folders."""

from dataclasses import replace
import hashlib
from pathlib import Path

from .atomic import atomic_bytes
from .codec import prepared_from_json
from .plan import SuiteProvenanceError


def verify_prepared(case):
    if case.artifact_path is not None:
        if not case.artifact_path.is_file():
            raise SuiteProvenanceError('Saved Case artifact is missing; this slot requires explicit repair')
        actual = hashlib.sha256(case.artifact_path.read_bytes()).hexdigest()
        if not case.artifact_sha256 or actual != case.artifact_sha256:
            raise SuiteProvenanceError('Saved Case artifact digest no longer matches its prepared identity')
    return case


def retain_prepared(directory, agent_id, case, existing=None):
    if existing is not None:
        saved = prepared_from_json(existing)
        if (saved.case_id, saved.content_sha256) != (case.case_id, case.content_sha256):
            raise SuiteProvenanceError('A logical Case cannot be replaced with different generated content')
        if case.artifact_path is not None:
            actual = hashlib.sha256(case.artifact_path.read_bytes()).hexdigest()
            if actual != saved.artifact_sha256:
                raise SuiteProvenanceError('A logical Case cannot be replaced with different artifact bytes')
        return verify_prepared(saved)
    if case.artifact_path is None:
        return case
    data = case.artifact_path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if case.artifact_sha256 is not None and digest != case.artifact_sha256:
        raise SuiteProvenanceError('Prepared Case bytes do not match the declared artifact digest')
    # Agent IDs are public labels, never filesystem paths supplied to a writer.
    agent_directory = hashlib.sha256(agent_id.encode()).hexdigest()[:24]
    path = Path(directory) / 'cases' / agent_directory / str(case.case_index) / 'case.json'
    if path.exists() and path.read_bytes() != data:
        raise SuiteProvenanceError('A previously published Case artifact cannot be overwritten')
    if not path.exists():
        atomic_bytes(path, data)
    return replace(case, artifact_path=path.resolve(), artifact_sha256=digest)

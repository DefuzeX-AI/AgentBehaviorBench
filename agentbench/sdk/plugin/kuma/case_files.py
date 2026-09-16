"""Host-side saved Case identity checks and immutable byte publication."""
import hashlib
import json
import tempfile
from pathlib import Path

from agentbench.runtime.contracts.execution import RunControl
from agentbench.sdk.common.case_identity import case_content_sha256
from agentbench.sdk.contracts import PreparedCase


def collection_artifact(directory: Path, reference: str) -> Path:
    """Resolve an exported Case file without accepting links or path aliases."""
    path = directory / Path(reference).name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
        raise ValueError(f'Case collection is missing its saved Case artifact: {reference}')
    return path.resolve()


def prepare_artifact(directory, entry, index, control):
    """Verify public identity on the host, then preserve the exact saved bytes.

    The container's pinned SDK performs full artifact/signature validation again
    before execution. Host checks deliberately do not import that dependency.
    """
    source = collection_artifact(directory / 'evaluation/cases', entry['artifact'])
    artifact = json.loads(source.read_text(encoding='utf-8'))
    if (not isinstance(artifact, dict) or artifact.get('schema_version') != 'kuma.case_artifact.v1'
            or not isinstance(artifact.get('case'), dict)):
        raise ValueError('Invalid saved SDK Case artifact')
    case = artifact['case']
    if artifact.get('origin') == 'official':
        # This is only the public prompt projection for BBA's content digest;
        # retain the entire signed artifact rather than reconstructing a Case.
        case = {'case_id': case.get('case_id'), 'inputs': [
            {'payload_type': 'text', 'payload': step['prompt']} for step in case['steps']]}
    elif artifact.get('origin') != 'custom':
        raise ValueError('Invalid saved SDK Case origin')
    if case.get('case_id') != entry['case_id']:
        raise ValueError('Saved SDK Case ID does not match its collection entry')
    if case_content_sha256(case) != entry['content_sha256']:
        raise ValueError('Saved SDK Case content does not match its collection entry')
    path, digest = freeze_artifact(
        source, directory / 'evaluation/prepared-cases' / f'case-{index + 1:04d}.json', control)
    return PreparedCase(index, entry['case_id'], path, entry['content_sha256'], digest)


def freeze_artifact(source: Path, target: Path, control: RunControl) -> tuple[Path, str]:
    """Copy SDK wire bytes atomically and return their explicit integrity digest."""
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    stream = tempfile.NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False)
    temporary = Path(stream.name)
    try:
        with source.open('rb') as incoming, stream:
            while block := incoming.read(1024 * 1024):
                control.check()
                digest.update(block)
                stream.write(block)
        temporary.chmod(0o444)
        temporary.replace(target)
        return target.resolve(), digest.hexdigest()
    finally:
        temporary.unlink(missing_ok=True)


def artifact_digest(path: Path, control: RunControl) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            control.check()
            digest.update(block)
    return digest.hexdigest()

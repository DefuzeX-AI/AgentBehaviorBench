"""KUMA-specific adaptation of ABB's private storage and remote telemetry."""
import inspect
from pathlib import Path


def storage_options(create_run, storage):
    if 'storage_path' not in inspect.signature(create_run).parameters:
        raise RuntimeError('This KUMA SDK lacks storage_path; upgrade kuma-defuzex. '
                           'ABB will not place a Case in the Agent workspace.')
    root = Path(storage)
    if not root.is_dir():
        raise ValueError('Private SDK storage was not mounted by the controller')
    return {'storage_path': root}


class KumaEvidenceSink:
    def __init__(self, capture):
        self.capture = capture

    def accept_span(self, span):
        # These are transported original ended spans, not spans regenerated from
        # text logs. Run.get_input has already opened the SDK capture window.
        self.capture.export_span(span)


def published_case(directory, index, workspace, files):
    """Restore a committed publication without another SDK generation request."""
    import hashlib
    import json
    from .compatibility import artifact_case
    from agentbench.sdk.common.case_identity import case_content_sha256
    root = Path(directory)
    path, record = root / 'case.json', root / 'publication.json'
    if not path.exists():
        return None
    if path.is_symlink() or record.is_symlink() or not record.is_file():
        raise ValueError('Published Case is incomplete; repair its original publication before generation')
    data = path.read_bytes()
    saved = json.loads(record.read_text(encoding='utf-8'))
    if saved.get('sha256') != hashlib.sha256(data).hexdigest() or saved.get('workspace') != workspace:
        raise ValueError('Published Case or workspace identity changed')
    entry = saved['entry']
    case = artifact_case(json.loads(data))
    if (entry.get('case_index') != index or entry.get('case_id') != case['case_id']
            or entry.get('content_sha256') != case_content_sha256(case)
            or entry.get('artifact') != f'.kuma/abb-case-{index + 1:04d}.json'):
        raise ValueError('Published Case identity does not match its slot')
    files.save('cases/' + Path(entry['artifact']).name, json.loads(data))
    return entry


def publish_case(directory, entry, workspace, files):
    import hashlib
    from agentbench.sdk.integration.artifacts import FileCaseArtifacts
    from agentbench.sdk.common.artifacts import Artifacts
    from agentbench.sdk.common.output_permissions import share_output
    destination = Path(directory)
    content = (files.directory / 'cases' / Path(entry['artifact']).name).read_bytes()
    FileCaseArtifacts(destination).publish_case(content)
    Artifacts(destination).save('publication.json', {
        'schema': 'abb.kuma.case-publication.v1', 'sha256': hashlib.sha256(content).hexdigest(),
        'entry': entry, 'workspace': workspace})
    share_output(destination)

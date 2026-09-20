"""Retain bounded final changed files using the pinned SDK's snapshots."""
from pathlib import Path
from agentbench.observe.store import redact


class ChangedFileExporter:
    def __init__(self, root, files):
        from kuma.evidence.tracking.snapshot import Snapshotter
        self.files = files
        self.snapshotter = Snapshotter(root)
        self.baseline = self.snapshotter.capture()

    def finish(self):
        from kuma.evidence.tracking.diff import compare_snapshots
        from kuma.repository.privacy import scan_sensitive_path, scan_sensitive_text
        final = self.snapshotter.capture()
        comparison = compare_snapshots(self.baseline, final, scope='container', upload_diff=False)
        manifest = {'schema': 'abb.changed_files.v1', 'status': 'complete',
                    'scope': 'changed_text_files', 'files': [], 'errors': list(final.errors)}
        for change in comparison.evidence.changes:
            entry = final.entries.get(change.path)
            candidate = Path(change.path)
            relative = candidate.relative_to(final.root).as_posix() if candidate.is_absolute() else candidate.as_posix()
            if '..' in Path(relative).parts:
                raise ValueError('SDK changed path escapes workspace')
            item = {'path': relative, 'change_type': change.change_type,
                    'status': 'omitted', 'reason': change.reason}
            manifest['files'].append(item)
            if change.change_type == 'deleted':
                item.update(status='deleted', reason=None)
                continue
            if entry is None or entry.file_type != 'file':
                item['reason'] = 'non_regular_file'
                continue
            text = entry.text_content
            if text is None:
                item['reason'] = entry.text_omission_reason or entry.scan_error or 'content_unavailable'
                continue
            if (scan_sensitive_path(change.path) or scan_sensitive_text(text, location=change.path)
                    or redact(text, self.files.secrets) != text):
                item['reason'] = 'sensitive_content'
                continue
            filename = f"workspace-files/{entry.sha256.removeprefix('sha256:')}.json"
            self.files.save(filename, {'content': text, 'encoding': 'utf-8'})
            item.update(status='exported', reason=None, artifact=filename,
                        size=entry.size, sha256=entry.sha256)
        if not final.complete or not comparison.evidence.complete or any(i['status'] == 'omitted' for i in manifest['files']):
            manifest['status'] = 'partial'
        self.files.save('workspace-artifacts.json', manifest)
        return manifest

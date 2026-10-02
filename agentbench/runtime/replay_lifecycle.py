"""Keep optional local replay failures separate from evaluation outcomes."""
import json
from pathlib import Path
from .workspace_replay import WorkspaceRecorder


class ReplayCapture:
    def __init__(self, root, destination, *, secrets=()):
        self.destination = Path(destination)
        self.recorder = None
        try:
            self.recorder = WorkspaceRecorder(root, destination, secrets=secrets)
        except Exception as exc:
            self._failure(exc)

    def _failure(self, exc):
        # No trace/log emission: replay diagnostics are local artifacts too.
        try:
            (self.destination / 'capture-error.json').write_text(json.dumps({
                'status': 'partial', 'error_type': type(exc).__name__,
                'message': 'Workspace recording is incomplete.'}), encoding='utf-8')
        except OSError:
            pass

    def checkpoint(self, reason, input_id):
        if self.recorder is not None:
            try:
                self.recorder.capture(reason, input_id=input_id, force=True)
            except Exception as exc:
                self._failure(exc)

    def finish(self):
        if self.recorder is not None:
            try:
                self.recorder.finish()
            except Exception as exc:
                self._failure(exc)

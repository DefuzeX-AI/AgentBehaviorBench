"""Runtime paths shared by trusted SDK controllers and isolated Agents."""
from dataclasses import dataclass
from pathlib import Path

REQUESTS = '/run/abb-channel/request'
RESPONSES = '/run/abb-channel/response'
STORAGE = '/run/abb-sdk-storage'


@dataclass(frozen=True)
class ExecutionChannel:
    requests: Path
    responses: Path

    @classmethod
    def create(cls, directory):
        root = Path(directory)
        paths = [root / 'request', root / 'response']
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o700)
        return cls(*paths)

    def mounts(self, *, controller=False):
        return ('--mount', f'type=bind,source={self.requests},target={REQUESTS}' + ('' if controller else ',readonly'),
                '--mount', f'type=bind,source={self.responses},target={RESPONSES}')

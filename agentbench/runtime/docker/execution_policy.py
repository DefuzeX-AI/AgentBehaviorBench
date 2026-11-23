"""Mounts for the single container running the SDK worker and the Agent."""
from pathlib import Path

from .policy import DockerPolicy


class ControllerExecutionPolicy:
    """Mount the workspace, SDK storage, optional replay and Case publications."""

    def __init__(self, storage, *, repository, target='/opt/abb-sdk-repo',
                 writable=False, replay=None, publications=()):
        self.storage = Path(storage).resolve()
        self.repository = Path(repository).resolve()
        self.target, self.writable = target, writable
        self.replay, self.publications = replay, publications

    def owned_directories(self):
        return (self.storage,)

    def shared_directories(self):
        return tuple(path for _, path in self.publications)

    def run_arguments(self):
        from agentbench.runtime.workspace_replay import REPLAY_MOUNT
        from agentbench.sdk.integration.context import STORAGE
        recording = ('--mount', f'type=bind,source={self.replay},target={REPLAY_MOUNT}') if self.replay else ()
        return (*DockerPolicy().run_arguments(), '--mount',
                f'type=bind,source={self.repository},target={self.target}' + ('' if self.writable else ',readonly'),
                '--mount', f'type=bind,source={self.storage},target={STORAGE}', *recording,
                *(arg for index, path in self.publications for arg in (
                    '--mount', f'type=bind,source={path},target=/run/abb-published/{index}')))

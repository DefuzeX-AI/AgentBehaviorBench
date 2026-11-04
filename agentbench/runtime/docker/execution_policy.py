"""Separate controller-private storage from the Agent's current-input channel."""
from pathlib import Path

from .policy import DockerPolicy


class ControllerExecutionPolicy:
    """Mount private SDK artifacts only in the trusted controller."""

    def __init__(self, storage, *, repository, target='/opt/abb-sdk-repo',
                 writable=False, replay=None, channel=None, publications=()):
        self.storage = Path(storage).resolve()
        self.repository = Path(repository).resolve()
        self.target, self.writable = target, writable
        self.replay, self.channel, self.publications = replay, channel, publications

    def owned_directories(self):
        return (self.storage,)

    def shared_directories(self):
        # The Agent and trusted controller mount this channel with separate
        # container users, so the controller runtime must grant group access.
        channel = ((self.channel.requests, self.channel.responses)
                   if self.channel is not None else ())
        return (*channel, *(path for _, path in self.publications))

    def run_arguments(self):
        from agentbench.runtime.workspace_replay import REPLAY_MOUNT
        from agentbench.sdk.integration.context import STORAGE
        recording = ('--mount', f'type=bind,source={self.replay},target={REPLAY_MOUNT}') if self.replay else ()
        return (*DockerPolicy().run_arguments(), '--mount',
                f'type=bind,source={self.repository},target={self.target}' + ('' if self.writable else ',readonly'),
                '--mount', f'type=bind,source={self.storage},target={STORAGE}', *recording,
                *(self.channel.mounts(controller=True) if self.channel else ()),
                *(arg for index, path in self.publications for arg in (
                    '--mount', f'type=bind,source={path},target=/run/abb-published/{index}')))


class AgentExecutionPolicy:
    def __init__(self, repository, target, writable, channel, output):
        self.repository, self.target = repository, target
        self.writable, self.channel, self.output = writable, channel, output

    def owned_directories(self):
        return (self.channel.requests, self.channel.responses, self.output)

    def run_arguments(self):
        return (*DockerPolicy().run_arguments(), '--mount',
                f'type=bind,source={self.repository},target={self.target}' +
                ('' if self.writable else ',readonly'), *self.channel.mounts())

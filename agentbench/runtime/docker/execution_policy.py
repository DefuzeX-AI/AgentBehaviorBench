"""Mount only the Agent workspace and its current-input channel."""
from .policy import DockerPolicy


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

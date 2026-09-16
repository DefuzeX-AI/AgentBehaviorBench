"""Failures shared by planning, individual builders and CLI orchestration."""


class BuildError(ValueError):
    """A build stage could not produce a validated integration file."""


class BuildPaused(BuildError):
    """An actionable incomplete result; already saved files remain available."""

    def __init__(self, status: str, messages):
        self.status, self.messages = status, tuple(messages)
        super().__init__("; ".join(self.messages))

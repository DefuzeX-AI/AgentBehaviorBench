"""Failures shared by planning, individual builders and CLI orchestration."""


class BuildError(ValueError):
    """A build stage could not produce a validated integration file."""


class BuildPaused(BuildError):
    """An actionable incomplete result; already saved files remain available."""

    def __init__(self, status: str, messages):
        self.status, self.messages = status, tuple(messages)
        super().__init__("; ".join(self.messages))


class ProviderResponseError(BuildError):
    """Safe provider diagnostics; optional checked content exists only for repair."""

    def __init__(self, message, *, diagnostics=None, previous_content=None):
        self.diagnostics = diagnostics or {}
        self.previous_content = previous_content
        super().__init__(message)


class StageResponseError(BuildError):
    """A terminal response failure; enclosing file loops must not retry it."""

    def __init__(self, message, *, diagnostics=None):
        self.diagnostics = diagnostics or {}
        super().__init__(message)

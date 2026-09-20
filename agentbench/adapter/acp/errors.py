"""Execution failures remain distinct from a Judge's behavioral verdict."""

class ACPError(RuntimeError):
    """An ACP operation failed; code and phase can be persisted by callers."""
    def __init__(self, message, *, code='protocol_error', phase='execution'):
        super().__init__(message)
        self.code, self.phase = code, phase
        # A lost response does not prove an operation is safe to repeat.
        self.retryable = False

"""Contract for stateless counting wire adapters."""
from typing import Protocol


class TokenCountProtocol(Protocol):
    name: str

    def normalize(self, body: dict) -> dict:
        """Return the input-bearing envelope or raise for unsupported content."""
        ...

    def response(self, tokens: int) -> dict:
        """Encode a calculated estimate using the caller's response schema."""
        ...

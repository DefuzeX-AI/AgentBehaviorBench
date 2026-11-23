"""Compatibility imports for the original ABB telemetry interface."""
from agentbench.harness.otel.compat.wire import context, timestamp, TransportedSpan, decode_span

__all__ = ['context', 'timestamp', 'TransportedSpan', 'decode_span']

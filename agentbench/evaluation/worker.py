"""Compatibility entry point for the KUMA worker's former module path."""

from agentbench.sdk.kuma_runtime.worker import execute, main

__all__ = ["execute", "main"]


if __name__ == "__main__":
    raise SystemExit(main())

"""Compatibility alias; implementation lives in sdk.kuma."""
import sys
from ..kuma import benchmark as _implementation
if __name__ == "__main__":
    raise SystemExit(_implementation.main())
sys.modules[__name__] = _implementation

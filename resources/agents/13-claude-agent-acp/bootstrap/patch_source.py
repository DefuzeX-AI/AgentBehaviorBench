"""Keep Claude ACP's background title call inside ABB's one-shot lifetime."""
from __future__ import annotations

from pathlib import Path
import sys


BEFORE = """      void this.requestGenerateTitle(session, fallback).catch((error) => {
        this.agent.logger.error(`Session ${this.sessionId}: session title update failed: ${error}`);
      });
"""
AFTER = """      await this.requestGenerateTitle(session, fallback);
"""


def patch(source: Path) -> None:
    text = source.read_text(encoding="utf-8")
    if text.count(BEFORE) != 1:
        raise RuntimeError("Claude ACP compatibility patch did not find its expected source block")
    source.write_text(text.replace(BEFORE, AFTER), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_source.py PATH", file=sys.stderr)
        return 2
    patch(Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Standalone entry used by the controlled network lab."""
import asyncio
import json
import sys
from probe.runner import run_suite

if __name__ == "__main__":
    result = asyncio.run(run_suite(json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    raise SystemExit(bool(result["failed"]))


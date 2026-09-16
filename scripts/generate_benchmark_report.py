#!/usr/bin/env python3
"""Generate the inspectable HTML report for a persisted benchmark campaign."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from benchmark_report.collect import collect_report  # noqa: E402
from benchmark_report.render import render_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    root = SCRIPT_DIR.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root, help="AgentBehaviorBench repository root")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("docs/Benchmark-Campaign-Ledger.json"),
        help="Ledger path, relative to --root unless absolute",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/analysis/benchmark-day-report-2026-09-14.html"),
        help="HTML output path, relative to --root unless absolute",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    output = args.output if args.output.is_absolute() else root / args.output
    data = collect_report(root, ledger)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(data), encoding="utf-8")
    print(f"Wrote {output}")
    print(
        "Summary: "
        f"runs={data['summary']['runs']} attempts={data['summary']['attempts']} "
        f"healthy={data['summary']['healthy']} failed={data['summary']['failed']} "
        f"judge_reports={data['summary']['judge_reports']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

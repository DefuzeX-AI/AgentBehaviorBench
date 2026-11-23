"""Explicit experimental export, live acceptance, and verification commands."""
import argparse
import json
from pathlib import Path

from agentbench.trajectory.atif.adapters import ADAPTER_NAMES


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--input", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--adapter", choices=ADAPTER_NAMES, action="append", default=[])
    export.add_argument("--allow-incomplete", action="store_true")
    export.add_argument("--bundle", action="store_true", help="Publish portable trace into a new child of --output")
    portable = commands.add_parser("verify-bundle")
    portable.add_argument("--input", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--input", type=Path, required=True)
    check.add_argument("--export", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--case", action="append", dest="cases", help="Run only named configured cases")
    run.add_argument("--bundle", action="store_true", help="Export and validate portable evidence after the run")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-bundle":
            from agentbench.trajectory.atif.bundle_validation import verify_bundle
            print(json.dumps(verify_bundle(args.input), ensure_ascii=False))
            return 0
        if args.command == "export" and args.bundle:
            from agentbench.trajectory.atif.bundle import export_bundle
            result = export_bundle(args.input, args.output, adapters=args.adapter, allow_incomplete=args.allow_incomplete)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == "export":
            from agentbench.trajectory.atif.export import export_run
            result = export_run(args.input, args.output, adapters=args.adapter, allow_incomplete=args.allow_incomplete)
            print(json.dumps(result.validation, ensure_ascii=False))
            return 0
        if args.command == "verify":
            from .acceptance import verify
            result = verify(args.input, args.export)
        else:
            from .runner import run_experiment
            result = run_experiment(args.config, args.output, names=args.cases, bundle=args.bundle)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["passed"] else 2
    except Exception as exc:
        from agentbench.observe.store import redact, environment_secrets
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "error": redact(str(exc), environment_secrets())}, ensure_ascii=False))
        return 2 if args.command == "verify-bundle" else 1


if __name__ == "__main__":
    raise SystemExit(main())

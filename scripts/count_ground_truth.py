"""Count Ground Truth issues and the Agents that carry them.

An issue is a ``resources/agents/<unit>/ground_truth/issue_<number>/`` directory;
it is usable when it holds ``verify.case.json``. This checks file presence and
layout, not whether a run reproduces the issue.
Run from any directory: python scripts/count_ground_truth.py
"""

import argparse
import json
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]


def inspect(root: Path) -> dict:
    agents = root / "resources" / "agents"
    if not agents.is_dir():
        raise ValueError(f"Agent directory does not exist: {agents}")

    issues = sorted(path for path in agents.glob("*/ground_truth/issue_*") if path.is_dir())
    rows = [{"agent": issue.parent.parent.name, "issue": issue.name,
             "verify_case": (issue / "verify.case.json").is_file()} for issue in issues]
    with_case = [row for row in rows if row["verify_case"]]
    return {
        "issue_directories": len(rows),
        "with_verify_case": len(with_case),
        "agents_with_issues": len({row["agent"] for row in with_case}),
        "missing_verify_case": [row for row in rows if not row["verify_case"]],
        "issues": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY,
                        help="ABB repository root (default: this script's repository)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--details", action="store_true", help="List every issue with a verify Case")
    args = parser.parse_args()
    result = inspect(args.root.resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for key in ("issue_directories", "with_verify_case", "agents_with_issues"):
        print(f"{key}: {result[key]}")
    for row in result["missing_verify_case"]:
        print(f"missing_verify_case: {row['agent']}/{row['issue']}")
    if args.details:
        for row in result["issues"]:
            if row["verify_case"]:
                print(f"{row['agent']}/{row['issue']}")


if __name__ == "__main__":
    main()

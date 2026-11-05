"""Count Ground Truth issues with a Case and saved run trajectories.

This checks file presence and layout, not whether a run reproduced the issue.
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
    rows = []
    for issue in issues:
        runs = issue / "runs"
        canonical = sorted(runs.glob("*/trajectory/*/trajectory.json"))
        other = sorted(runs.glob("*/trajectory.json"))
        rows.append({
            "agent": issue.parent.parent.name,
            "issue": issue.name,
            "verify_case": (issue / "verify.case.json").is_file(),
            "runs_directory": runs.is_dir(),
            "canonical_trajectories": len(canonical),
            "other_trajectories": len(other),
        })

    with_case = [row for row in rows if row["verify_case"]]
    with_runs = [row for row in with_case if row["runs_directory"]]
    with_trajectory = [row for row in with_runs
                       if row["canonical_trajectories"] or row["other_trajectories"]]
    loadable_layout = [row for row in with_runs if row["canonical_trajectories"]]
    return {
        "issue_directories": len(rows),
        "with_verify_case": len(with_case),
        "with_verify_case_and_runs_directory": len(with_runs),
        "with_verify_case_and_trajectory": len(with_trajectory),
        "with_loader_trajectory_layout": len(loadable_layout),
        "agents_with_trajectory": len({row["agent"] for row in with_trajectory}),
        "nonstandard_trajectory_layout": [row for row in with_trajectory
                                          if not row["canonical_trajectories"]],
        "runs_directory_without_trajectory": [row for row in with_runs
                                             if not row["canonical_trajectories"]
                                             and not row["other_trajectories"]],
        "issues": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY,
                        help="ABB repository root (default: this script's repository)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument("--details", action="store_true", help="List issues with trajectories")
    args = parser.parse_args()
    result = inspect(args.root.resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for key in ("issue_directories", "with_verify_case",
                "with_verify_case_and_runs_directory", "with_verify_case_and_trajectory",
                "with_loader_trajectory_layout", "agents_with_trajectory"):
        print(f"{key}: {result[key]}")
    for key in ("nonstandard_trajectory_layout", "runs_directory_without_trajectory"):
        for row in result[key]:
            print(f"{key}: {row['agent']}/{row['issue']}")
    if args.details:
        for row in result["issues"]:
            if row["verify_case"] and (row["canonical_trajectories"] or row["other_trajectories"]):
                print(f"{row['agent']}/{row['issue']}: "
                      f"{row['canonical_trajectories']} canonical, "
                      f"{row['other_trajectories']} other")


if __name__ == "__main__":
    main()

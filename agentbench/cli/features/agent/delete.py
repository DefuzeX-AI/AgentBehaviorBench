"""`agentbench agent delete`: unregister one Agent and archive its folder."""

from __future__ import annotations

from argparse import Namespace, RawDescriptionHelpFormatter
from pathlib import Path

from ..run import DEFAULT_REGISTRY_PATH


def configure_parser(commands) -> None:
    delete = commands.add_parser(
        "delete",
        help="Unregister an Agent and move its folder to cache/agent-trash.",
        description=(
            "Remove one Agent's registry entry and move its whole folder, including\n"
            "ground_truth/, to cache/agent-trash. Nothing is permanently erased.\n"
            "Stop runs, certifications and viewers that use this Agent first."
        ),
        epilog=(
            "Examples:\n"
            "  agentbench agent delete my-agent --dry-run\n"
            "  agentbench agent delete 01-my-agent"
        ),
        formatter_class=RawDescriptionHelpFormatter,
    )
    delete.add_argument("agent", metavar="AGENT",
                        help="Registered agent_id, or a numbered folder name such as 01-my-agent.")
    delete.add_argument("--agents-dir", metavar="DIRECTORY", type=Path,
                        default=DEFAULT_REGISTRY_PATH.parent / "agents",
                        help="Parent of numbered Agent folders (default: resources/agents).")
    delete.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    delete.add_argument("--dry-run", action="store_true",
                        help="Show what would be removed without changing files.")
    delete.add_argument("-y", "--yes", action="store_true", help="Delete without prompting.")
    delete.set_defaults(agent_handler=_delete,
                        agent_interrupted="Agent deletion interrupted; check cache/agent-trash "
                                          "and the registry before retrying.")


def _delete(args: Namespace) -> int:
    from agentbench.onboarding.remove import apply_removal, plan_removal

    plan = plan_removal(args.agent, agents_directory=args.agents_dir, registry_path=args.registry)
    print(f"Agent: {plan.agent_id or '(not registered)'}")
    print(f"Folder: {plan.unit or '(already missing)'}")
    print(f"Registry: {plan.registry_path}" + ("" if plan.agent_id else " (unchanged)"))
    print(f"Archive: {plan.archive_root}")
    print("Saved results, Docker images and .env are unchanged.")
    if args.dry_run:
        return 0
    if not args.yes:
        try:
            answer = input("Delete this Agent? [y/N]: ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled; nothing was changed.")
            return 0
    archived = apply_removal(plan)
    if plan.agent_id:
        print(f"Removed {plan.agent_id} from the registry.")
    if archived:
        print(f"Moved the folder to: {archived}")
        print("To restore, move it back and re-add its [[agents]] entry if it was registered.")
    if plan.agent_id:
        print("Refresh the Agent inventory documents with: python scripts/update_agent_docs.py")
    return 0

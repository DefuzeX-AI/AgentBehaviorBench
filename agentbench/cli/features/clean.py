"""Clear default local history by moving it into a recoverable archive."""
from agentbench.cli.history import PROJECT_ROOT, archive_history, history_targets
from .base import CommandFeature


def configure_parser(parser):
    parser.add_argument('--dry-run', action='store_true', help='List history without changing files.')
    parser.add_argument('-y', '--yes', action='store_true', help='Confirm cleanup without prompting; stop active runs first.')


def execute(args):
    try:
        targets = history_targets(PROJECT_ROOT)
        if not targets:
            print('No local result history to clean.')
            return 0
        print(f'History root: {PROJECT_ROOT / "results"}')
        for target in targets:
            print(f'  {target.name}')
        print('Scope: all files/directories under results, including traces, reports and SDK recovery state.')
        print('Agent source, .env, registry status, Docker images and custom output paths are unchanged.')
        print('Stop active runs and viewers before cleaning. History is archived, not permanently erased.')
        if args.dry_run:
            return 0
        if not args.yes and input('Move this history to .history-trash? [y/N]: ').strip().lower() not in ('y', 'yes'):
            print('Cancelled; history unchanged.')
            return 0
        archive = archive_history(targets, PROJECT_ROOT)
        print(f'Cleared {len(targets)} top-level entries. Recoverable archive: {archive}')
        print('To restore, stop runs/viewers and move archive contents back into results without overwriting newer files.')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Cleanup interrupted; check .history-trash if moving had started.')
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Cleanup failed: {exc}')
        return 1


FEATURE = CommandFeature(name='clean', help='Clear local result history (recoverable archive).',
                         description=__doc__, configure=configure_parser, execute=execute)

"""Clear default local history by moving it into a recoverable archive."""
from agentbench.cli.history import PROJECT_ROOT, archive_history, history_targets, protected_history
from .base import CommandFeature


def configure_parser(parser):
    parser.add_argument('--dry-run', action='store_true', help='List history without changing files.')
    parser.add_argument('-y', '--yes', action='store_true', help='Confirm cleanup without prompting; stop active runs first.')


def execute(args):
    try:
        targets = history_targets(PROJECT_ROOT)
        protected = protected_history(PROJECT_ROOT)
        if protected:
            print('Retained for saved Suites and their Attempt history:')
            for target, suites in protected.items():
                print(f'  {target.name} ({len(suites)} saved Suite(s))')
        if not targets:
            print('No unreferenced local result history to clean.' if protected else 'No local result history to clean.')
            return 0
        print(f'History root: {PROJECT_ROOT / "results"}')
        for target in targets:
            print(f'  {target.name}')
        print('Scope: unreferenced top-level entries under results; saved Suites and referenced artifacts stay in place.')
        print('Agent source, .env, registry status, Docker images and custom output paths are unchanged.')
        print('Stop active runs and viewers before cleaning. History is archived, not permanently erased.')
        if args.dry_run:
            return 0
        if not args.yes and input('Move this history to cache/history-trash? [y/N]: ').strip().lower() not in ('y', 'yes'):
            print('Cancelled; history unchanged.')
            return 0
        archive = archive_history(targets, PROJECT_ROOT)
        print(f'Cleared {len(targets)} top-level entries. Recoverable archive: {archive}')
        print('To restore, stop runs/viewers and move archive contents back into results without overwriting newer files.')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Cleanup interrupted; check cache/history-trash if moving had started.')
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Cleanup failed: {exc}')
        return 1


FEATURE = CommandFeature(name='clean', help='Archive unreferenced local result history.',
                         description=__doc__, configure=configure_parser, execute=execute)

"""Derive or show the trajectory.json step sequence of a saved execution."""
import json
import sys
from pathlib import Path

from .base import CommandFeature


def configure(parser):
    commands = parser.add_subparsers(dest='trajectory_command', required=True)
    build = commands.add_parser('build', help='Derive trajectory.json from the raw evidence of one attempt directory')
    build.add_argument('directory', type=Path, help='Attempt directory (run.json or evaluation/ inside)')
    build.add_argument('--write', action='store_true', help='Save trajectory.json beside the evidence instead of printing it')
    build.add_argument('--force', action='store_true', help='Replace an existing trajectory.json whose content differs')
    show = commands.add_parser('show', help='Render the saved or derived trajectory as step text')
    show.add_argument('directory', type=Path)
    show.add_argument('--mode', choices=('full', 'truncate_middle', 'response_only'), default='truncate_middle')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False).encode('utf-8')


def execute(args):
    from agentbench.project import project_root
    from agentbench import trajectory
    directory = args.directory.resolve()
    if not directory.is_dir():
        print(f'Not a directory: {directory}', file=sys.stderr)
        return 1
    try:
        if args.trajectory_command == 'show':
            from agentbench.trajectory.render import render
            print(render(trajectory.load(directory, project_root=project_root()), args.mode))
            return 0
        value = trajectory.validate(trajectory.build(directory, project_root=project_root()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Trajectory unavailable: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    if not args.write:
        sys.stdout.write(_canonical(value).decode('utf-8') + '\n')
        return 0
    target = directory / trajectory.FILENAME
    if target.exists() and not args.force:
        existing = target.read_bytes()
        if existing != _canonical(value):
            try:
                same = json.loads(existing).get('sources') == value.get('sources')
            except ValueError:
                same = False
            print(f'{target} already exists with different content'
                  + (' (same sources; rebuilt with a newer builder?)' if same else '')
                  + '; use --force to replace it', file=sys.stderr)
            return 1
    from agentbench.sdk.common.artifacts import Artifacts
    Artifacts(directory).save(trajectory.FILENAME, value)
    print(f"Saved {target} ({value['status']}, {len(value['steps'])} steps)")
    return 0 if value['status'] != 'failed' else 1


FEATURE = CommandFeature(name='trajectory', help='Build or show the derived step sequence of a saved execution.',
                         description=__doc__, configure=configure, execute=execute)

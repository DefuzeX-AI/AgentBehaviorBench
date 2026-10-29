"""Export historical repair projects and validate external source with the GT Case."""
import contextlib
import json
from pathlib import Path
import sys

from .base import CommandFeature


def configure(parser):
    from agentbench.project import project_root
    commands = parser.add_subparsers(dest='operation', required=True)
    generate = commands.add_parser('genProject', help='Export pinned source/ and only the Issue object')
    generate.add_argument('agent_id')
    generate.add_argument('--issue', type=int, required=True)
    generate.add_argument('--output', type=Path, required=True, help='New absolute directory outside ABB')
    generate.add_argument('--records-dir', type=Path, help='Host provenance directory outside the exported project')
    run = commands.add_parser('run', help='Replay the original GT Case against frozen external source')
    run.add_argument('agent_id')
    run.add_argument('--issue', type=int, required=True)
    run.add_argument('--source', type=Path, required=True, help='Absolute path to the modified source/ directory')
    run.add_argument('--runs', type=int, default=3, help='Independent repair executions (default: 3)')
    run.add_argument('--results-dir', type=Path)
    run.add_argument('--model', help='Target model override; oracle uses OPENROUTER_MODEL')
    run.add_argument('--timeout', type=float, default=2400, help='Timeout per Case execution in seconds')
    run.add_argument('--env-file', type=Path)
    result = commands.add_parser('result', help='Read a saved repair result without executing anything')
    result.add_argument('--experiment', type=Path, required=True)
    for command in (generate, run, result):
        command.add_argument('--root', type=Path, default=project_root())


def execute(args):
    from agentbench.experiments.exp3 import Experiment3
    from agentbench.cli.environment import load_execution_environment
    from agentbench.observe.store import environment_secrets, redact
    environ = {}
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.operation == 'result':
                value = Experiment3.result(args.experiment)
            elif args.operation == 'genProject':
                value = Experiment3(args.root, environ={}).gen_project(args.agent_id, issue=args.issue,
                    output=args.output, records_dir=args.records_dir)
            else:
                environ = load_execution_environment(args.env_file).environ
                value = Experiment3(args.root, environ=environ).run(args.agent_id, issue=args.issue,
                    source=args.source, runs=args.runs, results_dir=args.results_dir,
                    model=args.model, timeout=args.timeout)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({'error': {'type': type(exc).__name__,
            'message': redact(str(exc), environment_secrets(environ))}}, ensure_ascii=False))
        return 1


FEATURE = CommandFeature(name='exp3', help='Export and validate Issue repair projects',
                         description=__doc__, configure=configure, execute=execute)

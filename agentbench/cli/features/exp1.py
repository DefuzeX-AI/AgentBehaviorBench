"""Run Issue-level behavioural failure detection from an existing Case directory."""
import contextlib
import json
from pathlib import Path
import sys

from .base import CommandFeature


def configure(parser):
    from agentbench.project import project_root
    commands = parser.add_subparsers(dest='operation', required=True)
    run = commands.add_parser('run', help='Execute imported Cases once, then match Issue GT')
    run.add_argument('agent_id')
    run.add_argument('--case-dir', type=Path, required=True)
    run.add_argument('--tests', type=int, default=50, help='Execution budget per Issue (1-50; default 50)')
    run.add_argument('--workers', type=int, default=1, help='Concurrent Issues (one Case worker per Issue)')
    run.add_argument('--results-dir', type=Path)
    run.add_argument('--prompt-template', type=Path, help='Record the shared testing prompt template')
    run.add_argument('--scenario-file', type=Path, help='Record this Agent\'s shared scenario')
    run.add_argument('--model', help='Target model override; oracle uses OPENROUTER_MODEL')
    run.add_argument('--timeout', type=float, default=2400)
    match = commands.add_parser('match', help='Assess saved trajectories without executing Cases')
    match.add_argument('--experiment', type=Path, required=True)
    match.add_argument('--retry-failed', action='store_true', help='Explicitly retry failed/interrupted oracle calls')
    result = commands.add_parser('result', help='Read saved Detection@k results')
    result.add_argument('--experiment', type=Path, required=True)
    for subparser in (run, match, result):
        subparser.add_argument('--root', type=Path, default=project_root())
        subparser.add_argument('--env-file', type=Path)


def execute(args):
    from agentbench.experiments.exp1 import Experiment1
    from agentbench.cli.environment import load_execution_environment
    from agentbench.observe.store import environment_secrets, redact
    environ = {}
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.operation == 'result':
                value = Experiment1.result(args.experiment)
            else:
                environ = load_execution_environment(args.env_file).environ
                service = Experiment1(args.root, environ=environ)
                if args.operation == 'match':
                    value = service.match(args.experiment, retry_failed=args.retry_failed)
                else:
                    value = service.run(args.agent_id, args.case_dir, tests=args.tests, workers=args.workers,
                        results_dir=args.results_dir, prompt_template=args.prompt_template,
                        scenario_file=args.scenario_file, model=args.model, timeout=args.timeout)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({'error': {'type': type(exc).__name__,
            'message': redact(str(exc), environment_secrets(environ))}}, ensure_ascii=False))
        return 1


FEATURE = CommandFeature(name='exp1', help='Run behavioural failure detection and report Detection@k',
                         description=__doc__, configure=configure, execute=execute)

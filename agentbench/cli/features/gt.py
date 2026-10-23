"""Re-evaluate saved evidence without re-running or generating Agent cases."""
from pathlib import Path
from .base import CommandFeature


def configure(parser):
    parser.add_argument('--suite', required=True, type=Path)
    parser.add_argument('--env-file')


def execute(args):
    from agentbench.cli.environment import load_project_environment, execution_environment_snapshot
    from agentbench.evaluation import EvaluationService
    from agentbench.project import project_root
    load_project_environment(args.env_file)
    try:
        result = EvaluationService(project_root(), environ=execution_environment_snapshot().environ).evaluate_gt(args.suite, output=print)
        return 0 if result['status'] == 'completed' and not result['warnings'] else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'GT matching unavailable: {type(exc).__name__}')
        return 1


FEATURE = CommandFeature(name='gt', help='Match saved Suite executions against Agent ground truth.',
                         description=__doc__, configure=configure, execute=execute)

"""Run saved Cases under current code or explicitly changed model/step settings."""

from argparse import ArgumentParser, Namespace

from agentbench.cli.environment import execution_environment_snapshot, load_project_environment
from agentbench.cli.sessions.configuration import resolve_suite
from agentbench.cli.sessions.reuse import execute_reuse
from agentbench.cli.terminal_ui.presentation import print_suite_summary

from .base import CommandFeature
from .resume import _progress


def configure_parser(parser: ArgumentParser):
    parser.add_argument('suite', help='Original Suite ID, directory, or events.json path.')
    parser.add_argument('--suite-root', help='Root containing the original Suite ID.')
    parser.add_argument('--output-root', help='Parent directory for the new Suite; defaults to the original parent.')
    parser.add_argument('--env-file', help='Current credential/default file; secrets are never copied from a plan.')
    parser.add_argument('--model', help='Agent model for the new Suite; defaults to the saved model.')
    parser.add_argument('--max-steps', type=int, help='Positive SDK max_steps option for the new Suite.')


def execute(args: Namespace):
    try:
        load_project_environment(args.env_file)
        environment = execution_environment_snapshot().environ
        source = resolve_suite(args.suite, args.suite_root)
        execution = execute_reuse(source, environ=environment, root=args.output_root,
            model=args.model, max_steps=args.max_steps, on_event=_progress,
            on_created=lambda directory: print(f'New Suite: {directory.name}\nResult artifact: {directory / "events.json"}'))
        print_suite_summary(execution.result, print)
        print(f'View: agentbench view {execution.directory / "events.json"}')
        return 0 if execution.result.passed else 1
    except KeyboardInterrupt:
        print('New Suite interrupted; its saved Cases and results are retained.')
        return 130
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f'Case reuse could not complete: {exc}')
        return 2


FEATURE = CommandFeature('reuse', 'Run all saved Cases in a linked new Suite.',
    'Keep the original Case inputs while recording fresh code, model settings and execution results.',
    configure_parser, execute)

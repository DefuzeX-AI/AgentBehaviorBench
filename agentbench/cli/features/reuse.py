"""Run saved Cases under current code or explicitly changed model/step settings."""

from argparse import ArgumentParser, Namespace

from agentbench.cli.environment import execution_environment_snapshot, load_project_environment
from agentbench.cli.sessions.reuse_target import resolve_reuse_target
from agentbench.cli.sessions.reuse import execute_reuse
from agentbench.cli.terminal_ui.presentation import print_suite_summary
from agentbench.cli.viewer_service import find_viewer
from agentbench.project import project_root

from .base import CommandFeature
from .resume import _progress


def configure_parser(parser: ArgumentParser):
    parser.add_argument('suite', help='Suite ID/path (all Cases), or Case ID, artifact run ID, saved Case/attempt path (one Case).')
    parser.add_argument('--suite-root', help='Directory to search for saved Suites; defaults to project results and indexed Suites.')
    parser.add_argument('--agent', help='Exact Agent ID; use with --case and a Suite source.')
    parser.add_argument('--case', dest='case_number', type=int, help='One-based Case number; use with --agent.')
    parser.add_argument('--output-root', help='Only join/create reuse Suites under this directory; new batches otherwise use the original parent.')
    parser.add_argument('--env-file', help='Current credential/default file; secrets are never copied from a plan.')
    parser.add_argument('--model', help='Agent model for the new Suite; defaults to the saved model.')
    parser.add_argument('--max-steps', type=int, help='Positive SDK max_steps option for the new Suite.')


def execute(args: Namespace):
    try:
        load_project_environment(args.env_file)
        environment = execution_environment_snapshot().environ
        source = resolve_reuse_target(args.suite, args.suite_root, agent_id=args.agent, case_number=args.case_number)
        def created(directory):
            print(f'Reuse Suite: {directory.name}\nResult artifact: {directory / "events.json"}')
            viewer = find_viewer(project_root())
            if viewer:
                print(f'View: {viewer}/suite/{directory.name}/')
            else:
                print(f'View: agentbench view {directory / "events.json"}')
        execution = execute_reuse(source.directory, selection=source.selection, environ=environment, root=args.output_root,
            model=args.model, max_steps=args.max_steps, on_event=_progress,
            on_created=created)
        print_suite_summary(execution.result, print)
        return execution.result.exit_code
    except KeyboardInterrupt:
        print('Reuse command interrupted; accepted tasks and saved results are retained in its Suite.')
        return 130
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f'Case reuse could not complete: {exc}')
        return 2


FEATURE = CommandFeature('reuse', 'Rerun a saved Case or Suite with fresh Agent execution and judging.',
    'Keep the original Case inputs while recording fresh code, model settings and execution results.',
    configure_parser, execute)

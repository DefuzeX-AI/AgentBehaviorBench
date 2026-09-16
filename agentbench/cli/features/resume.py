"""Continue a persisted Suite or explicitly retry one unfinished Case."""

from argparse import ArgumentParser, Namespace

from agentbench.cli.environment import load_project_environment, execution_environment_snapshot
from agentbench.cli.sessions.configuration import resolve_suite
from agentbench.cli.sessions.recovery import execute_recovery
from agentbench.cli.terminal_ui.presentation import print_suite_summary, case_event_status
from agentbench.harness.session import SuiteLockedError
from .base import CommandFeature


def configure_parser(parser: ArgumentParser):
    parser.add_argument('suite', help='Saved Suite ID, directory, or events.json path.')
    parser.add_argument('--suite-root', help='Directory containing saved Suites; defaults to results/suites.')
    parser.add_argument('--env-file', help='Credential/default file; secrets are never read from saved plans.')


def configure_retry(parser: ArgumentParser):
    configure_parser(parser)
    parser.add_argument('--agent', required=True, help='Exact Agent ID from the original Suite.')
    parser.add_argument('--case', dest='case_number', required=True, type=int, help='One-based Case number.')


def execute(args: Namespace):
    try:
        load_project_environment(args.env_file)
        environment = execution_environment_snapshot().environ
        directory = resolve_suite(args.suite, args.suite_root)
        selection = None
        if hasattr(args, 'case_number'):
            if args.case_number < 1:
                raise ValueError('Case number must be at least one')
            selection = {(args.agent, args.case_number - 1)}
        result = execute_recovery(directory, environ=environment, selection=selection,
                                  replay=selection is not None, on_event=_progress)
        print_suite_summary(result, print)
        print(f'Result artifact: {directory / "events.json"}')
        print(f'View: agentbench view {directory / "events.json"}')
        return 0 if result.passed else 1
    except KeyboardInterrupt:
        print('Recovery interrupted; saved Cases and results retained.')
        return 130
    except (OSError, ValueError, RuntimeError, KeyError, SuiteLockedError) as exc:
        print(f'Recovery could not complete: {exc}')
        return 2


def _progress(event):
    if event.get('event') in {'case_started', 'case_completed', 'retry_scheduled'}:
        label = event.get('case_index', 0) + 1
        print(f"[{event.get('agent_id')} | case={label} | attempt={event.get('attempt_number', 1)}] "
              f"{event['event']}: {case_event_status(event)}")


FEATURE = CommandFeature('resume', 'Continue unfinished work in a saved Suite.',
                         'Reuse saved Cases and recover unfinished operations.', configure_parser, execute)
RETRY_FEATURE = CommandFeature('retry', 'Retry one unfinished Case using its original inputs.',
                               'Recover the original request or explicitly rerun a failed Case from its first Input.',
                               configure_retry, execute)

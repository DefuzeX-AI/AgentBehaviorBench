"""Evaluate one Agent on independent Cases using the selected evaluation SDK."""
import math
from dataclasses import replace
from agentbench.cli.execution import run_benchmark_session
from agentbench.cli.trace_runtime import build_trace_suite_runner
from agentbench.cli.terminal_ui import LLMActivity
from agentbench.cli.viewer import start_viewer_server
from agentbench.cli.features.certify import _default_output_path
from pathlib import Path
from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH
from .observe import model_name
from ..environment import load_project_environment
from ..sdk import configure_sdk_parser, sdk_arguments
from agentbench.observe.catalog import enabled_agents, select_agent, resolve_agent
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
from agentbench.sdk import evaluation_plan


def configure_parser(parser):
    parser.add_argument('selection', nargs='?', help='Enabled Agent number or ID')
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--model', type=model_name)
    configure_sdk_parser(parser)
    parser.add_argument('--no-view', action='store_true', help='Save results without starting the live viewer.')
    parser.add_argument('--llm-trace', choices=('off', 'terminal'), default='off')
    parser.add_argument('--llm-trace-max-bytes', type=int, default=DEFAULT_TRACE_MAX_BYTES)
    parser.add_argument('--result-output', type=Path, help='ABB result JSON naming base (independent of SDK output)')
    parser.add_argument('--output', type=Path, help='Override the SDK output option')
    parser.add_argument('--timeout', type=float, help='Override the SDK timeout option (seconds)')
    parser.add_argument('--cases', type=int, help='Number of independent Cases (default: Registry case count)')
    parser.add_argument('--max-steps', type=int, help='SDK upper bound on dialogue steps per Case')


def execute(args):
    try:
        if args.timeout is not None and (not math.isfinite(args.timeout) or args.timeout <= 0):
            raise ValueError('Timeout must be finite and positive')
        for name in ('cases', 'max_steps'):
            value = getattr(args, name, None)
            if value is not None and value < 1:
                raise ValueError(f'{name} must be a positive integer')
        selected = sdk_arguments(args)
        options = dict(selected.get('sdk_options', {}))
        # Only explicit aliases are forwarded. Each SDK owns its defaults.
        for name in ('output', 'timeout', 'max_steps'):
            value = getattr(args, name, None)
            if value is not None:
                options[name] = value
        plan = evaluation_plan(selection=selected.get('sdk_selection'), options=options)
        load_project_environment(args.env_file)
        records = enabled_agents(args.registry)
        selection = args.selection
        if selection is None:
            print('Enabled Agents:')
            for index, record in enumerate(records, 1):
                print(f'{index}. {record["agent_id"]} status={record.get("status")}')
            selection = input('选择 Agent 编号（q 退出）: ').strip()
            if selection.lower() == 'q':
                return 0
        agent = resolve_agent(select_agent(records, selection), args.registry)
        if getattr(args, 'cases', None) is not None:
            agent = replace(agent, case_count=args.cases)
        print(f'Evaluation: {agent.case_count} independent Case(s) using {plan.selection.reference.name}; '
              'selected services may incur charges.', flush=True)
        output = args.result_output or _default_output_path(args.registry, agent.agent_id, command="evaluate")
        if args.output is not None:
            print('--output configures the SDK only; --result-output selects the ABB result JSON.')
        activity = LLMActivity(print)
        runner = build_trace_suite_runner(mode=args.llm_trace, max_bytes=args.llm_trace_max_bytes,
            output_fn=print, model=args.model, activity_sink=activity,
            sdk_selection=plan.selection, sdk_options=plan.options)
        execution = run_benchmark_session((agent,), runner=runner, output_path=output,
            output_fn=print, viewer_starter=None if args.no_view else start_viewer_server,
            llm_activity=activity, input_fn=input)
        if execution.result is None:
            return execution.exit_code
        items = execution.result.items
        if any(item.error_type or item.completed_case_count != item.requested_case_count for item in items):
            return 1
        reports = [benchmark.report for item in items for benchmark in item.benchmarks]
        if not reports or any(report is None for report in reports):
            print('Evaluation failed: SDK completed without a Judge report')
            return 1
        print(f'Judge: {reports[-1].status}')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Evaluation interrupted; artifacts retained.')
        return 130
    except Exception as exc:
        print(f'Evaluation failed: {exc}')
        return 1


FEATURE = CommandFeature(name='evaluate', help='Evaluate one Agent on independent SDK Cases',
                         description=__doc__, configure=configure_parser, execute=execute)

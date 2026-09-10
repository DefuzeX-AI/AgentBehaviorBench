"""One official Case with KUMA and the Agent in the same container."""
import json
import math
import os
from pathlib import Path
from .base import CommandFeature
from .run import DEFAULT_REGISTRY_PATH
from .observe import model_name
from ..environment import load_project_environment
from agentbench.observe.catalog import enabled_agents, select_agent, resolve_agent
from agentbench.sdk.kuma_runtime.benchmark import ContainerBenchmarkRunner


def configure_parser(parser):
    parser.add_argument('selection', nargs='?', help='Enabled Agent number or ID')
    parser.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--model', type=model_name)
    parser.add_argument('--sdk-source', type=Path, default=Path(__file__).resolve().parents[4] / 'Defuze-SDK')
    parser.add_argument('--output', type=Path, default=Path('results/observe'))
    parser.add_argument('--timeout', type=float, default=2400)


def execute(args):
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError('Timeout must be finite and positive')
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
        load_project_environment(args.env_file)
        environ = dict(os.environ)
        if args.model:
            environ['OPENROUTER_MODEL'] = args.model
        print('Official evaluation: one Case, at most one Input; Case/Judge may incur charges.', flush=True)
        result = ContainerBenchmarkRunner(environ=environ, options={
            'output': args.output, 'sdk_source': args.sdk_source, 'timeout': args.timeout}).run(agent)
        print(f'Judge: {result.report.status}')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Evaluation interrupted; artifacts retained.')
        return 130
    except Exception as exc:
        print(f'Evaluation failed: {exc}')
        return 1


FEATURE = CommandFeature(name='evaluate', help='One official SDK Case inside the Agent container',
                         description=__doc__, configure=configure_parser, execute=execute)

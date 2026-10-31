"""JSON interface to the same EvaluationService used by Python clients."""
import json
from pathlib import Path
from .base import CommandFeature


def configure(parser):
    from agentbench.project import project_root
    parser.add_argument('--root', type=Path, default=project_root())
    parser.add_argument('--env-file', type=Path)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('agent').add_argument('agent_id')
    prepare = commands.add_parser('prepare')
    prepare.add_argument('agent_id')
    prepare.add_argument('--revision', required=True)
    execute = commands.add_parser('execute')
    execute.add_argument('agent_id')
    execute.add_argument('--case-file', type=Path, required=True)
    execute.add_argument('--results-dir', type=Path)
    execute.add_argument('--judge')
    execute.add_argument('--model')
    execute.add_argument('--timeout', type=float, default=2400)
    execute.add_argument('--max-steps', type=int)
    execute.add_argument('--revision', help='Prepare and execute this exact historical commit')
    for name in ('result', 'evidence', 'attachment', 'submit-judge', 'gt'):
        command = commands.add_parser(name)
        command.add_argument('--suite', type=Path, required=True)
        if name in ('evidence', 'attachment', 'submit-judge'):
            command.add_argument('--run-id', required=True)
        if name == 'attachment':
            command.add_argument('--path', required=True)
        if name == 'submit-judge':
            command.add_argument('--report', type=Path, required=True)


def execute(args):
    import contextlib
    import sys
    from agentbench.evaluation import EvaluationService
    from agentbench.cli.environment import load_project_environment, execution_environment_snapshot
    try:
        # Provider progress belongs on stderr; stdout is always one JSON document.
        with contextlib.redirect_stdout(sys.stderr):
            load_project_environment(args.env_file)
            loaded = execution_environment_snapshot()
            service = EvaluationService(args.root, environ=loaded.environ)
            operation = args.operation
            if operation == 'agent':
                value = service.agent(args.agent_id)
            elif operation == 'prepare':
                value = service.prepare(args.agent_id, args.revision).describe()
            elif operation == 'execute':
                document = json.loads(args.case_file.read_text(encoding='utf-8-sig'))
                if not isinstance(document, dict) or document.get('schema') != 'abb.cases.v1':
                    raise ValueError('Expected abb.cases.v1 collection')
                value = service.execute(args.agent_id, document.get('cases'), results_dir=args.results_dir,
                    judge=args.judge, model=args.model, timeout=args.timeout,
                    max_steps=args.max_steps, concurrency=loaded.concurrency,
                    target=service.prepare(args.agent_id, args.revision) if args.revision else None)
            elif operation == 'result':
                value = service.result(args.suite)
            elif operation == 'evidence':
                value = service.evidence(args.suite, args.run_id)
            elif operation == 'attachment':
                value = service.attachment(args.suite, args.run_id, args.path)
            elif operation == 'submit-judge':
                value = service.submit_judge(args.suite, args.run_id,
                    json.loads(args.report.read_text(encoding='utf-8-sig')))
            else:
                value = service.evaluate_gt(args.suite)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        from agentbench.observe.store import redact, environment_secrets
        print(json.dumps({'error': {'type': type(exc).__name__,
            'message': redact(str(exc), environment_secrets())}}, ensure_ascii=False))
        return 1


FEATURE = CommandFeature(name='api', help='Use the shared evaluation API with JSON input/output',
                         description=__doc__, configure=configure, execute=execute)

"""Panda and the selected Agent execute in the same container process."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4
from agentbench.sdk.common.artifacts import Artifacts, plain
from agentbench.sdk.common.input_binding import InputBinding
from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.runtime.agentcontainer.worker import execute as invoke_agent, configure_trust
from agentbench.runtime.agentcontainer.config import tomllib


async def execute(root, output, settings):
    from panda_sdk import create_run
    from opentelemetry.sdk.trace import TracerProvider
    files = Artifacts(output)
    provider = TracerProvider()
    session = AgentSession()
    summary = {'phase': 'case_generation', 'sdk': 'panda', 'steps': [], 'pid': os.getpid()}
    try:
        configure_trust()
        manifest = tomllib.loads((root / 'agent.toml').read_text())
        run = create_run(repo_path=root / 'agent', **settings,
            **({'api_key': os.environ['PANDA_API_KEY'], 'model': os.environ['PANDA_MODEL']}
               if settings.get('provider') == 'openrouter' else {}))
        summary.update(run_id=run.run_id, case_id=run.case_id, agent_id=manifest['agent_id'])
        files.save('case.json', run._case)
        binding = InputBinding.from_file(root / 'evaluation/input-contract.json')
        conversation = binding.new_conversation()
        while (item := run.get_input(full=True)) is not None:
            folder = f'inputs/{len(summary["steps"]) + 1:04d}'
            files.save(f'{folder}/input.json', item)
            request = {'schema': 'abb.invocation.v1', 'run_id': uuid4().hex,
                'session_id': run.run_id, 'agent_id': manifest['agent_id'],
                'framework': manifest['framework'],
                'observation_context': {'case_id': run.case_id, 'input_id': item.input_id},
                'input': conversation.prepare(binding.map(item.payload))}
            files.save(f'{folder}/request.json', request)
            summary['phase'] = 'execution'
            code = await invoke_agent(root, output / folder / 'request.json', output / folder,
                                      provider=provider, session=session)
            result = json.loads((output / folder / 'result.json').read_text())
            if code != 0 or result['status'] != 'succeeded':
                raise RuntimeError('Agent execution failed; see step result')
            summary['phase'] = 'submission_and_judge'
            run.submit(result['output'])
            files.save(f'{folder}/submission.json', run.history[-1].submission)
            summary['steps'].append({'input_id': item.input_id, 'directory': folder,
                                     'agent_pid': os.getpid()})
            conversation.commit(result)
        if run.report is None:
            raise RuntimeError('Panda returned no Judge report')
        files.save('judge/report.json', {**plain(run.report), 'run_id': run.run_id, 'case_id': run.case_id})
        summary.update(phase='finished', execution='succeeded', judge='received')
        return 0
    except Exception as exc:
        summary.update(execution='failed', error_type=type(exc).__name__)
        return 1
    finally:
        await session.aclose()
        files.save('session.json', session.snapshot())
        provider.force_flush()
        provider.shutdown()
        files.save('manifest.json', summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    parser.add_argument('--settings', type=Path, default=Path('/run/abb-input/evaluation.json'))
    args = parser.parse_args()
    return asyncio.run(execute(args.agent_root, args.output, json.loads(args.settings.read_text())))


if __name__ == '__main__':
    raise SystemExit(main())

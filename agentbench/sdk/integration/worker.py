"""Default isolated SDK controller using SDKRun and AgentExecutionSession."""
import argparse
import asyncio
import importlib
import json
from pathlib import Path
from uuid import uuid4

from agentbench.observe.store import redact
from agentbench.sdk.common.artifacts import Artifacts, plain
from agentbench.sdk.common.output_permissions import share_output
from .agent import ManagedAgentSession
from .artifacts import FileCaseArtifacts
from .cases import case_bytes, digest, pack_case, snapshot, unpack_case
from .dialogue import drive_run, submit_result


class RecordedEvidence:
    """Existing EvidenceSink with on-disk original spans available to the SDK."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.steps = []
        self.span_count = 0

    def accept_span(self, span):
        # DirectoryAgentSession has already saved the full original export.
        self.span_count += 1

    def spans(self):
        from .telemetry import decode_span
        for directory in self.steps:
            with Path(directory / 'spans.jsonl').open(encoding='utf-8') as stream:
                for line in stream:
                    yield decode_span(json.loads(line))


def load_factory(reference):
    module, separator, name = reference.partition(':')
    if not separator or not name.isidentifier() or not all(part.isidentifier() for part in module.split('.')):
        raise ValueError('SDK factory must be a module:function reference')
    factory = getattr(importlib.import_module(module), name)
    if not callable(factory):
        raise ValueError('SDK factory is not callable')
    return factory


def _close_run(run, primary=None):
    # Resource release is optional; never infer a request retry from an error.
    close = getattr(run, 'close', None)
    if close is not None:
        try:
            close()
        except Exception as exc:
            if primary is None:
                raise
            primary.sdk_cleanup_error = str(exc)


def generate_cases(factory, root, repository, settings, files):
    entries = []
    for index in settings['case_indices']:
        publication = settings.get('case_publications', {}).get(str(index))
        published = Path(publication) / 'case.json' if publication else None
        if published is not None and Path(published).exists():
            if Path(published).is_symlink():
                raise ValueError('Published Case must not be a link')
            record = published.parent / 'publication.json'
            if Path(record).is_symlink() or not Path(record).is_file():
                raise ValueError('Case publication is incomplete; reconcile it before generating again')
            content = Path(published).read_bytes()
            if json.loads(Path(record).read_bytes()).get('sha256') != digest(content):
                raise ValueError('Published Case was modified')
            document = json.loads(content)
            unpack_case(document, factory=settings['sdk_factory'], index=index)
            if document['workspace'] != settings.get('workspace'):
                raise ValueError('Published Case belongs to a different workspace')
        else:
            if published is not None:
                marker = published.parent / 'generation.json'
                if Path(marker).exists():
                    raise ValueError('Previous generation has no committed Case; reconcile the SDK request before retrying')
                Artifacts(published.parent).save('generation.json', {
                    'status': 'started', 'factory': settings['sdk_factory'], 'case_index': index})
            run = factory(case=None, repo_path=repository, agent_root=root, case_index=index,
                          storage_path=Path(settings['private_storage']), evidence=None, **settings['sdk_options'])
            primary = None
            try:
                document = pack_case(run.case, factory=settings['sdk_factory'], index=index,
                                     workspace=settings.get('workspace'))
                if redact(document, files.secrets) != document:
                    raise ValueError('SDK generated a Case containing a credential')
                if published is not None:
                    content = case_bytes(document)
                    FileCaseArtifacts(published.parent).publish_case(content)
                    Artifacts(published.parent).save('publication.json', {'sha256': digest(content)})
                    Artifacts(published.parent).save('generation.json', {'status': 'committed',
                        'factory': settings['sdk_factory'], 'case_index': index})
                    share_output(published.parent)
            except BaseException as exc:
                primary = exc
                raise
            finally:
                _close_run(run, primary)
        relative = f'cases/{index:04d}.json'
        files.save(relative, document)
        # Hash the bytes actually persisted, independent of JSON formatting.
        content = Path(files.directory / relative).read_bytes()
        entries.append({'case_index': index, 'case_id': document['case']['case_id'],
                        'artifact': relative, 'artifact_sha256': digest(content),
                        'content_sha256': digest(case_bytes(document['case']))})
        files.save('case-collection.json', entries)
    return entries


async def execute_case(factory, root, repository, settings, files, summary, *, session=None):
    path = Path(settings['private_storage']) / 'case.json'
    content = Path(path).read_bytes()
    if digest(content) != settings['expected_artifact_sha256']:
        raise ValueError('Prepared Case artifact changed before execution')
    document = json.loads(content)
    case = unpack_case(document, factory=settings['sdk_factory'], index=settings.get('source_case_index', settings['case_index']))
    if (case['case_id'] != settings['expected_case_id']
            or digest(case_bytes(case)) != settings['expected_content_sha256']
            or document['workspace'] != settings.get('workspace')):
        raise ValueError('Prepared Case identity or workspace mismatch')
    files.save('case.json', document)
    evidence = RecordedEvidence(files.directory)
    run = factory(case=case, repo_path=repository, agent_root=root,
                  storage_path=Path(settings['private_storage']), case_index=settings['case_index'],
                  evidence=evidence, **settings['sdk_options'])
    primary = None
    try:
        if snapshot(run.case) != document['case']:
            raise ValueError('SDK changed the saved Case while loading it')
        if not isinstance(run.run_id, str) or not run.run_id.strip():
            raise ValueError('SDK Run needs a non-empty run_id')
        summary.update(run_id=run.run_id, case_id=case['case_id'], phase='execution')
        async with ManagedAgentSession(output=files.directory, settings=settings, session=session) as agent:
            async def invoke(item, folder):
                return await agent.invoke({
                    'schema': 'abb.invocation.v1', 'run_id': uuid4().hex, 'session_id': run.run_id,
                    'agent_id': settings['agent_id'], 'framework': settings['framework'],
                    'input': item.payload, 'observation_context': {
                        'case_id': case['case_id'], 'input_id': item.input_id}}, folder, evidence)

            async def step(current_run, item, invoke):
                number = len(summary['steps']) + 1
                limit = settings['sdk_options'].get('max_steps')
                if limit is not None and number > limit:
                    raise ValueError('SDK exceeded the requested max_steps')
                relative = f'steps/{number:04d}'
                folder = files.directory / relative
                record = {'input_id': item.input_id, 'directory': relative, 'submitted': False}
                summary['steps'].append(record)
                files.save(f'{relative}/input.json', {'input_id': item.input_id, 'payload': item.payload})
                evidence.steps.append(folder)
                files.save('manifest.json', summary)
                result = await invoke(item, folder)
                if result.get('status') not in ('succeeded', 'failed', 'timeout', 'cancelled', 'aborted'):
                    raise ValueError('Unknown Agent execution status')
                telemetry = json.loads(Path(folder / 'otel-status.json').read_bytes())
                if telemetry.get('status') != 'complete':
                    raise ValueError('Agent telemetry is incomplete; SDK result was not submitted')
                # ManagedAgentSession persists redacted results before submission.
                summary['phase'] = 'submission'
                report = submit_result(current_run, result)
                record.update(submitted=True, status=result['status'])
                files.save(f'{relative}/submission.json', {
                    'input_id': item.input_id, 'result': result, 'submitted': True})
                summary['phase'] = 'execution'
                files.save('manifest.json', summary)
                return report

            def before_input():
                summary['phase'] = 'input'

            # Record Judge failures distinctly, including failures after submit
            # has committed. Vendor request reconciliation remains SDK-owned.
            report = await drive_run(run, invoke, step=step, before_input=before_input, judge=False)
            if not summary['steps']:
                raise ValueError('SDK returned no inputs')
            summary['phase'] = 'judge'
            if snapshot(run.case) != document['case']:
                raise ValueError('SDK mutated the generation snapshot during execution')
            from .dialogue import judge_run
            if settings.get('execution_only'):
                summary['judge_delivery_status'] = 'not_requested'
            else:
                if report is None:
                    report = judge_run(run)
                files.save('judge/report.json', {key: plain(getattr(report, key)) for key in (
                    'status', 'confidence', 'issues', 'evidence_gaps')})
            summary.update(phase='finished', status='succeeded', run_state=run.state,
                           history_count=len(run.history), evidence='complete', span_count=evidence.span_count)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _close_run(run, primary)


async def execute(root, output, settings, *, session=None):
    files = Artifacts(Path(output))
    summary = {'schema': 'abb.sdk.execution.v1', 'status': 'running', 'steps': [], 'phase': 'startup'}
    try:
        mode = settings['mode']
        if mode not in ('generate', 'execute', 'context'):
            raise ValueError('Unknown SDK worker mode')
        if mode == 'execute' and not settings.get('isolated_agent'):
            raise ValueError('Execution requires the isolated Agent channel')
        if mode == 'context':
            from agentbench.runtime.agentcontainer.environment import observe_environment
            from agentbench.sdk.common.agent_context import with_environment
            from agentbench.sdk.common.workspace import workspace_policy
            from agentbench.runtime.agentcontainer.config import tomllib
            policy = workspace_policy(tomllib.loads((Path(root) / 'agent.toml').read_text()))
            workspace = ({'path': policy.path, 'initial_state': policy.initial_state,
                          'fixture': policy.fixture} if policy.path else None)
            environment = observe_environment(settings.get('execution_environment'), workspace=workspace)
            files.save('agent-context.json', with_environment(settings['agent_context'], environment))
            summary.update(status='succeeded', phase='context')
            return 0
        factory = load_factory(settings['sdk_factory'])
        repository = Path((settings.get('workspace') or {}).get('path') or '/opt/abb-sdk-repo')
        if mode == 'generate':
            summary['phase'] = 'generation'
            generate_cases(factory, Path(root), repository, settings, files)
            summary.update(status='succeeded', phase='generated')
        else:
            await execute_case(factory, Path(root), repository, settings, files, summary, session=session)
        return 0
    except Exception as exc:
        summary.update(status='failed', error_type=type(exc).__name__, error=str(exc))
        if getattr(exc, 'sdk_cleanup_error', None):
            summary['sdk_cleanup_error'] = exc.sdk_cleanup_error
        files.save('error.json', summary)
        return 1
    finally:
        try:
            files.save('manifest.json', summary)
        finally:
            share_output(files.directory)
            if settings.get('private_storage'):
                share_output(settings['private_storage'])
            for publication in settings.get('case_publications', {}).values():
                share_output(publication)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-root', type=Path, default=Path('/opt/agent'))
    parser.add_argument('--output', type=Path, default=Path('/run/abb-output'))
    parser.add_argument('--settings', type=Path, default=Path('/run/abb-input/evaluation.json'))
    args = parser.parse_args()
    try:
        settings = json.loads(args.settings.read_bytes())
        from agentbench.runtime.contracts.environment import ENVIRONMENT_FILE
        environment_path = args.settings.parent / ENVIRONMENT_FILE
        if environment_path.exists() and isinstance(settings, dict):
            settings['execution_environment'] = json.loads(environment_path.read_bytes())
        if not isinstance(settings, dict):
            raise ValueError('SDK settings must be an object')
    except (OSError, ValueError) as exc:
        Artifacts(args.output).save('error.json', {'phase': 'startup', 'error': str(exc)})
        share_output(args.output)
        return 1
    return asyncio.run(execute(args.agent_root, args.output, settings))


if __name__ == '__main__':
    raise SystemExit(main())

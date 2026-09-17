"""Case selection import/generation, separated from Case execution."""
import json
import shutil
from uuid import uuid4

from agentbench.runtime.contracts.execution import DockerCleanupError, RunCancelled
from agentbench.sdk.common.artifacts import Artifacts
from agentbench.sdk.contracts import PreparationFailure, PreparedCaseBatch
from agentbench.observe.store import redact

from .case_files import collection_artifact, prepare_artifact
from .diagnostics import collect_artifacts, evaluation_failure, read_diagnostic, unreadable_reason
from .generation import SCHEMA, selected_indices, validate_collection, validate_entries
from .generation_failures import SHARED_GENERATION_BLOCKS


def _case_files(directory):
    """Name saved Case files even when their content cannot be read."""
    try:
        names = sorted(path.name for path in (directory / 'evaluation/cases').glob('*.json'))
    except OSError:
        return 'unknown'
    return ', '.join(names) or 'none'


def prepare_batch(runner, registration, *, evaluator, case_indices=None,
                  on_progress=None, allow_partial=True):
    """Prepare only selected original slots and retain per-slot generation errors.

    Explicit imported collections remain complete and strictly validated. A
    generated collection may be partial only for this optional batch API.
    """
    runner.control.check()
    runner.validate_sdk(registration)
    count = registration.case_count
    indices = selected_indices(count, case_indices)
    if not indices:
        return PreparedCaseBatch(())
    identity = runner._identity(registration, phase='generate', case_index=None, case_id=None)
    directory, primary_error = None, None

    def ready(path):
        nonlocal directory
        directory = path
        runner._artifacts_ready(registration, on_progress, path, identity,
                                f'Preparing {len(indices)} distinct Cases')

    if runner.case_collection is None:
        try:
            directory = evaluator(
                registration, output=runner.output, environ=runner.environ,
                timeout=runner.timeout, max_steps=runner.max_steps, generation_count=count,
                generation_indices=indices, partial_generation=allow_partial,
                trace_sink=runner.trace_sink, trace_max_bytes=runner.trace_max_bytes,
                **runner._runtime_options(identity), on_artifacts_ready=ready)
        except (RunCancelled, DockerCleanupError):
            raise
        except Exception as exc:
            if not allow_partial or directory is None:
                raise
            primary_error = exc
    else:
        directory = runner.output.resolve() / uuid4().hex
        Artifacts(directory, environ=runner.environ).save('run.json', {
            **identity, 'schema': 'abb.case_collection.import.v1', 'run_id': directory.name,
            'artifact_run_id': directory.name, 'status': 'running',
            'source': str(runner.case_collection.resolve())})

    files = Artifacts(directory, environ=runner.environ)
    try:
        runner.control.check()
        if runner.case_collection is not None:
            collection = json.loads(runner.case_collection.read_text())
            validate_collection(collection, count=count)
            source_cases = runner.case_collection.resolve().parent / 'cases'
            target_cases = directory / 'evaluation/cases'
            target_cases.mkdir(parents=True)
            for entry in collection['cases']:
                runner.control.check()
                source = collection_artifact(source_cases, entry['artifact'])
                shutil.copyfile(source, target_cases / source.name)
            files.save('evaluation/case-collection.json', collection)
        else:
            collection = read_diagnostic(directory, 'evaluation/case-collection.json')
            if not collection:
                # An unreadable collection is not a failed generation: the Cases may
                # already be generated and billed. Say so instead of discarding them.
                # The artifact detail appended by evaluation_failure names the file,
                # its owner and its mode.
                if unreadable_reason(directory, 'evaluation/case-collection.json') is not None:
                    raise evaluation_failure(
                        directory, 'Case batch was written but the host cannot read it; '
                        f'generated Case files on disk: {_case_files(directory)}',
                        environ=runner.environ)
            if not allow_partial:
                if read_diagnostic(directory, 'run.json').get('status') != 'succeeded':
                    raise evaluation_failure(directory, 'Case batch generation failed', environ=runner.environ)
                validate_collection(collection, count=count)
        batch = _accept_collection(runner, directory, collection, count, indices,
                                   allow_partial=allow_partial and runner.case_collection is None,
                                   primary_error=primary_error)
        accepted = len(batch.cases)
        complete = accepted == len(indices)
        files.save('evaluation/batch-selection.json', {
            'requested_count': count, 'selected_case_indices': indices,
            'accepted_count': accepted, 'status': 'accepted' if complete else 'partial',
            'failures': batch.failures, 'unattempted_indices': batch.unattempted_indices})
        status = read_diagnostic(directory, 'run.json')
        # Partial acceptance does not turn a failed generation container into a
        # successful one; its original transport/cleanup diagnostics remain.
        files.save('run.json', {**status, 'status': 'succeeded' if complete else 'failed',
                               'validation': 'succeeded' if complete else 'partial'})
        return batch
    except Exception as exc:
        files.save('evaluation/batch-selection.json', {
            'requested_count': count, 'accepted_count': 0, 'status': 'rejected', 'error': str(exc)})
        status = read_diagnostic(directory, 'run.json')
        files.save('run.json', {**status, 'status': 'cancelled' if runner.control.cancelled else 'failed',
                               'validation': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)})
        raise


def _accept_collection(runner, directory, collection, count, indices, *, allow_partial, primary_error):
    """Accept validated files independently, retaining original Case slot identity."""
    diagnostics = collect_artifacts(directory, read_diagnostic(directory, 'run.json'), environ=runner.environ)
    secrets = Artifacts(directory, environ=runner.environ).secrets
    if not collection:
        fallback = primary_error or evaluation_failure(directory, 'Case batch generation failed', environ=runner.environ)
        sdk_error = diagnostics.get('sdk_error', {})
        return PreparedCaseBatch((), (_failure(indices[0], sdk_error, diagnostics, fallback, secrets),), indices[1:])
    if collection.get('schema') != SCHEMA or collection.get('requested_count') != count:
        raise ValueError('Case collection does not match the requested selection')
    entries = collection.get('cases')
    if not isinstance(entries, list):
        raise ValueError('Case collection must contain a list of Cases')
    # New workers publish explicit indices; legacy output can only be a prefix.
    indexed = {entry.get('case_index', position): entry for position, entry in enumerate(entries)
               if isinstance(entry, dict)}
    if len(indexed) != len(entries):
        raise ValueError('Case collection contains invalid or duplicate Case slots')
    selected_indices(count, indexed)
    failures = _recorded_failures(collection, indices, diagnostics)
    active = collection.get('active_case_index')
    if active is not None:
        if type(active) is not int or active not in indices or active in indexed or active in failures:
            raise ValueError('Invalid active Case generation slot')
        failures[active] = _failure(active, {
            'error_type': 'InterruptedGeneration', 'code': 'request_state_unknown',
            'error_message': 'Generation was interrupted; reconcile the original SDK request before generating again',
        }, diagnostics)
    if set(indexed) & set(failures):
        raise ValueError('Case collection marks the same slot prepared and failed')
    prepared, accepted_entries = [], []
    for index in indices:
        if index not in indexed:
            continue
        runner.control.check()
        entry = {**indexed[index], 'case_index': index}
        try:
            validate_entries([*accepted_entries, entry], count=count)
            case = prepare_artifact(directory, entry, index, runner.control)
        except RunCancelled:
            raise
        except Exception as exc:
            if not allow_partial:
                raise
            failures[index] = _failure(index, {}, diagnostics, exc, secrets)
        else:
            prepared.append(case)
            accepted_entries.append(entry)
    unattempted = tuple(index for index in indices if index not in indexed and index not in failures)
    return PreparedCaseBatch(tuple(prepared), tuple(failures.values()), unattempted)


def _recorded_failures(collection, indices, artifacts):
    result = {}
    for item in collection.get('failures', []):
        if not isinstance(item, dict) or type(item.get('case_index')) is not int:
            raise ValueError('Invalid Case preparation failure')
        index = item['case_index']
        if index not in indices:
            continue
        if index in result:
            raise ValueError('Duplicate Case preparation failure')
        result[index] = _failure(index, item, artifacts)
    return result


def _failure(index, item, artifacts, fallback=None, secrets=()):
    request = item.get('request') or {}
    code = item.get('code')
    artifacts = {**artifacts, 'phase': 'case_generation'}
    unknown = code in {'request_state_unknown', 'network_error', 'operation_wait_timeout',
                       'request_in_progress', 'operation_state_unavailable'}
    if request.get('status') == 'failed':
        unknown = False
    elif request.get('status') in {'prepared', 'queued', 'running', 'succeeded'}:
        unknown = True  # Even succeeded CaseGen is not proof of an exported Case.
    if unknown:
        artifacts['recovery'] = {
            'action': 'inspect_request', 'automatic': False, 'allow_replay': False,
            'phase': 'case_generation', 'client_request_id': item.get('client_request_id'),
            'reason': 'Inspect the original Case generation request before creating new paid work'}
    elif code in SHARED_GENERATION_BLOCKS:
        artifacts['recovery'] = {
            'action': 'blocked', 'automatic': False, 'pause_preparation': True,
            'phase': 'case_generation', 'reason': 'Shared SDK credential or service block stopped generation'}
    elif request.get('status') == 'failed':
        artifacts['recovery'] = {
            'action': 'generate_case', 'automatic': False, 'allow_replay': True,
            'phase': 'case_generation', 'client_request_id': item.get('client_request_id'),
            'reason': 'Original Case generation request failed; an explicit request may generate this missing slot'}
    if request:
        artifacts['generation_request'] = request
    message = item.get('error_message') or item.get('message') or str(fallback or 'Case generation failed')
    if code in ('network_error', 'network_timeout') and artifacts.get('sdk_base_url'):
        # An unreachable Backend is usually a configuration question; say which one.
        message = f"{message} (KUMA backend: {artifacts['sdk_base_url']})"
    return PreparationFailure(
        index, item.get('error_type') or item.get('type') or type(fallback).__name__,
        redact(message, secrets),
        phase=item.get('phase') or 'case_generation', code=item.get('code'),
        retryable=item.get('retryable'), client_request_id=item.get('client_request_id'),
        request_id=item.get('request_id'), artifacts=artifacts)

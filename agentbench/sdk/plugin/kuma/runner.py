"""KUMA submission ledger and trace-evidence handshake.

These history/state/extension semantics belong to KUMA, not the SDK contract.
"""
from agentbench.sdk.common.artifacts import Artifacts, plain
from agentbench.observe.store import TraceStore


async def drive_run(run, invoke, directory, *, provider, repo_path=None):
    """Deliver current Inputs sequentially; leave context entirely to the Agent.

    Args:
        run: Initialized KUMA Run owning the Case and submission history.
        invoke: Async (payload, step_directory, provider) callable returning the
            native result envelope. Its caller owns the Agent session lifetime.
        directory: Destination for this Run's step artifacts and summary.
        provider: Shared trace provider flushed before each submission.
        repo_path: Optional SDK repository for Judge recovery diagnostics.
    Returns:
        Persisted summary of execution, evidence, submissions and Judge state.

    SDK creation and provider attachment happen before this loop, in its caller.
    Input folders use local ordinal IDs, never untrusted SDK identifiers as paths.
    Each payload is delivered unchanged, without history, summaries or old outputs.
    """
    files = Artifacts(directory)
    directory.mkdir(parents=True, exist_ok=True)
    trace = TraceStore(directory / 'sdk.jsonl', run.run_id, source='sdk')
    summary = {'run_id': run.run_id, 'case_id': run.case_id, 'phase': 'input',
               'execution': 'pending', 'otel': 'pending', 'submission': 'pending',
               'judge': 'pending', 'evidence': 'pending', 'steps': []}
    try:
        while True:
            summary['phase'] = 'input'
            item = run.get_input(full=True)
            if item is None:
                break
            number = len(summary['steps']) + 1
            relative = f'inputs/{number:04d}'
            files.save(f'{relative}/input.json', item)
            trace.record('input_delivered', input_id=item.input_id, case_id=run.case_id,
                         artifact=f'{relative}/input.json')
            payload = item.payload
            files.save(f'{relative}/context.json', {
                'input_delivery': 'current_input', 'context_owner': 'agent',
                'session_id': run.run_id, 'input_id': item.input_id})
            files.save(f'{relative}/mapped-input.json', payload)
            trace.record('input_mapped', input_id=item.input_id, case_id=run.case_id,
                         artifact=f'{relative}/mapped-input.json')
            summary['phase'] = 'execution'
            result = await invoke(payload, directory / relative, provider)
            files.save(f'{relative}/result.json', result)
            trace.record('agent_returned', input_id=item.input_id, case_id=run.case_id,
                         artifact=f'{relative}/result.json')
            succeeded = result['status'] == 'succeeded'
            summary['execution'] = ('failed' if not succeeded or summary['execution'] == 'failed'
                                    else 'succeeded')
            summary['phase'] = 'otel'
            import json
            trace_status = json.loads((directory / relative / 'otel-status.json').read_text())
            summary['otel'] = ('incomplete' if trace_status['status'] != 'complete'
                               or summary['otel'] == 'incomplete' else 'complete')
            if not provider.force_flush():
                summary['otel'] = 'incomplete'
            before = len(run.history)
            step = {'input_id': item.input_id, 'directory': relative, 'committed': False}
            summary['steps'].append(step)
            summary['phase'] = 'submission'
            try:
                trace.record('submission_started', input_id=item.input_id, case_id=run.case_id)
                if succeeded:
                    run.submit(output=result['output'], status='completed')
                else:
                    terminal = {'timeout': 'timeout', 'cancelled': 'aborted', 'aborted': 'aborted'}.get(result['status'], 'failed')
                    run.submit(status=terminal, error=f'Agent execution {terminal}; see local diagnostics')
            except Exception:
                if len(run.history) > before:
                    summary['phase'] = 'judge'
                raise
            finally:
                committed = run.history[before:]
                if committed:
                    step['committed'] = True
                    summary['submission'] = 'committed'
                    files.save(f'{relative}/submission.json', committed[0].submission)
                    submission = plain(committed[0].submission)
                    step['submission_status'] = submission['status']
                    step['capture_status'] = submission.get('capture_status', {})
                    trace.record('submission_committed', input_id=item.input_id, case_id=run.case_id,
                                 artifact=f'{relative}/submission.json')
                    # KUMA Submission recursively freezes JSON as MappingProxyType.
                    # Inspect the detached JSON snapshot already used for persistence,
                    # so a valid immutable trace is not mistaken for missing evidence.
                    evidence = submission['extensions'].get('trace_evidence')
                    files.save(f'{relative}/evidence.json', evidence)
                    capture_status = submission.get('capture_status', {})
                    traces = capture_status.get('traces', {})
                    summary['evidence'] = ('captured' if isinstance(evidence, dict)
                        and traces.get('status') in ('complete', 'partial') and summary['evidence'] != 'missing' else 'missing')
                    tool_status = [{'span_id': span.get('span_id'), 'tool_content_status': span['tool_content_status']}
                                   for span in (evidence or {}).get('spans', ()) if 'tool_content_status' in span]
                    files.save(f'{relative}/capture-status.json', {
                        'input_id': item.input_id, 'capture_status': capture_status,
                        'tool_content_status': tool_status,
                        'trace_summary': {key: evidence.get(key) for key in ('reasons', 'missing', 'dropped_count')}
                                         if isinstance(evidence, dict) else None})
                files.save('manifest.json', summary)
        summary['phase'] = 'judge'
        if run.report is not None:
            files.save('judge/report.json', run.report)
            trace.record('judge_received', case_id=run.case_id, artifact='judge/report.json')
            summary['judge'] = 'received'
            summary['phase'] = 'finished'
        else:
            summary['judge'] = 'missing'
    except Exception as exc:
        summary['error'] = {'type': type(exc).__name__, 'message': str(exc),
                            'code': getattr(exc, 'code', None),
                            'retryable': getattr(exc, 'retryable', None),
                            'client_request_id': getattr(exc, 'client_request_id', None),
                            'request_id': getattr(exc, 'request_id', None)}
        if summary['phase'] == 'judge':
            summary['judge'] = 'failed'
            request_id = getattr(exc, 'client_request_id', None)
            if repo_path is not None:
                # Persist only the SDK's public read-only request projection.
                # A retryable flag is not evidence that an operation is pending.
                from .request_recovery import inspect_requests
                try:
                    # A poll that dies after the judgment was accepted raises without
                    # a client_request_id, yet that is the failure recovery exists for.
                    # The ledger holds the record either way; match it on this Run.
                    candidates = ([inspect_requests(repo_path, request_id)] if request_id
                                  else inspect_requests(repo_path))
                    matching = [request for request in candidates
                                if request.get('run_id') == run.run_id and request.get('case_id') == run.case_id
                                and request.get('request_type') == 'judgment']
                    if matching:
                        summary['request'] = max(matching, key=lambda request: request.get('updated_at') or 0)
                except Exception:
                    pass  # Never replace the primary error with failed inspection.
        elif summary['phase'] == 'execution':
            summary['execution'] = 'failed'
        elif summary['phase'] == 'submission':
            summary['submission'] = 'failed'
        # Do not cancel completed history after a Judge failure; it may be recoverable.
        if run.state in ('ready', 'input_delivered'):
            run.cancel()
    finally:
        files.save('manifest.json', summary)
    return summary

"""One SDK Run, strict handshake, no duplicate submissions or automatic reruns."""
from .artifacts import Artifacts


async def drive_run(run, binding, invoke, directory, *, provider):
    """invoke(payload, step_directory, provider) returns the native result envelope.

    SDK creation and provider attachment happen before this loop, in its caller.
    Input folders use local ordinal IDs, never untrusted SDK identifiers as paths.
    """
    files = Artifacts(directory)
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
            summary['phase'] = 'input_contract'
            payload = binding.map(item.payload)
            files.save(f'{relative}/mapped-input.json', payload)
            summary['phase'] = 'execution'
            result = await invoke(payload, directory / relative, provider)
            files.save(f'{relative}/result.json', result)
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
                if succeeded:
                    run.submit(output=result['output'], status='completed')
                else:
                    run.submit(status='failed', error='Agent execution failed; see local diagnostics')
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
                    files.save(f'{relative}/evidence.json',
                               committed[0].submission.extensions.get('trace_evidence'))
                    evidence = committed[0].submission.extensions.get('trace_evidence')
                    summary['evidence'] = ('missing' if not evidence or not evidence.get('spans')
                                           or summary['evidence'] == 'missing' else 'captured')
                files.save('manifest.json', summary)
        summary['phase'] = 'judge'
        if run.report is not None:
            files.save('judge/report.json', run.report)
            summary['judge'] = 'received'
            summary['phase'] = 'finished'
        else:
            summary['judge'] = 'missing'
    except Exception as exc:
        summary['error'] = {'type': type(exc).__name__, 'message': str(exc),
                            'code': getattr(exc, 'code', None),
                            'request_id': getattr(exc, 'request_id', None)}
        if summary['phase'] == 'judge':
            summary['judge'] = 'failed'
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

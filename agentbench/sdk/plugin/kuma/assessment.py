"""Forward observed public text and attribute the isolated target's return value.

Internal model messages and graph state are never promoted to public messages.
An invocation without public capture keeps an honest empty/incomplete bundle;
explicit output attribution can support partial review on compatible services.
"""
import hashlib
from collections.abc import Mapping


def public_message_bundle(result):
    """Translate the adapter's optional text capture using KUMA's validator."""
    from kuma import collect_public_messages
    from kuma.evidence.assessment_contract import validate_public_messages

    capture = result.get('public_messages')
    if capture is None:
        return collect_public_messages([])
    if (not isinstance(capture, Mapping)
            or set(capture) - {'messages', 'complete', 'redacted'}
            or type(capture.get('complete')) is not bool
            or not isinstance(capture.get('messages'), (list, tuple))
            or type(capture.get('redacted', False)) is not bool):
        raise ValueError('Invalid public message capture')
    messages = []
    for index, message in enumerate(capture['messages']):
        if (not isinstance(message, Mapping) or set(message) != {'content'}
                or not isinstance(message['content'], str)):
            raise ValueError('Invalid public message capture')
        content = message['content']
        messages.append({'message_id': f'message-{index}', 'sequence': index,
                         'source_event_index': index, 'source_event_id': None,
                         'actor': 'target_agent', 'content': content,
                         'content_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()})
    reasons = [] if capture['complete'] else ['source_incomplete']
    if capture.get('redacted'):
        reasons.append('redacted')
    return validate_public_messages({
        'public_messages': messages,
        'coverage': {'public_messages': 'partial' if reasons else 'complete',
                     'execution': 'unavailable', 'network': 'unavailable', 'reasons': reasons}})


def submission_options(result):
    """SDK-only options for a result returned by the current target invocation.

    This names the producer of the entire return value, not speakers quoted
    inside it. Empty outputs and failed/aborted invocations are not attributed
    as completed output. No runtime span actors are inferred from span names.
    """
    options = {'public_messages': public_message_bundle(result)}
    output = result.get('output')
    nonempty = not (output is None or isinstance(output, str) and not output.strip()
                   or isinstance(output, (Mapping, list, tuple)) and not output)
    if result['status'] == 'succeeded' and nonempty:
        options['agent_output_actor'] = 'target_agent'
    return options


def submit_result(run, result):
    """Keep KUMA evidence options out of the generic SDK submission contract."""
    options = submission_options(result)
    if result['status'] == 'succeeded':
        return run.submit(output=result['output'], status='completed', **options)
    status = {'timeout': 'timeout', 'cancelled': 'aborted', 'aborted': 'aborted'}.get(
        result['status'], 'failed')
    return run.submit(status=status, error=result.get('error'), **options)

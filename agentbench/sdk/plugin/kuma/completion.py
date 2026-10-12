"""Validate a full history or an explicitly terminated, committed Case prefix."""


def validate_input_prefix(case, summary, last_result):
    expected = [item['input_id'] for item in case['inputs']]
    actual = [step['input_id'] for step in summary['steps']]
    if not expected or len(set(expected)) != len(expected) or not actual:
        raise ValueError('Incomplete or duplicate submitted Inputs')
    if actual == expected:
        if summary.get('unexecuted_inputs') or summary.get('termination'):
            raise ValueError('Completed history cannot contain unexecuted Inputs')
        return
    terminal = summary.get('termination') or {}
    if (actual != expected[:len(actual)] or len(actual) >= len(expected)
            or summary.get('execution') != 'failed'
            or last_result.get('status') not in ('failed', 'timeout', 'aborted', 'cancelled')
            or last_result.get('session_usable') is not False
            or terminal != {'input_id': actual[-1], 'status': last_result['status'],
                            'reason': 'session_unusable'}
            or summary.get('unexecuted_inputs') != expected[len(actual):]):
        raise ValueError('Incomplete or duplicate submitted Inputs')

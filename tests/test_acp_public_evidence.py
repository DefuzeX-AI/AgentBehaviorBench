from agentbench.observe.result import sanitize_result


def test_runtime_redaction_cannot_keep_complete_message_coverage():
    secret = 'test-only-credential-value-123456'
    result, receipt = sanitize_result({
        'status': 'succeeded',
        'output': 'done',
        'public_messages': {'messages': [{'content': f'Value {secret}'}], 'complete': True},
    }, (secret,))
    assert 'public_messages' in receipt['fields']
    capture = result['public_messages']
    assert secret not in capture['messages'][0]['content']
    assert capture['complete'] is False
    assert capture['redacted'] is True

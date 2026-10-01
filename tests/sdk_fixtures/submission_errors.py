"""Offline container acceptance through the native Agent, worker and KUMA."""
import asyncio
import json
from pathlib import Path

from tests.sdk_fixtures import agent_owned_session as fixture


async def main():
    expected_error = "This request exceeds your plan's set usage limit."
    fixture.AGENT_SOURCE = fixture.AGENT_SOURCE.replace(
        'Intentional Agent failure after committed SQLite work', expected_error)
    root = Path('/tmp/submission-error-agent')
    fixture.write_agent(root)
    output = Path('/artifacts')
    verification = await fixture.execute_case(
        root, Path('/tmp/submission-error-work'), output,
        ['remember blue', 'fail'], ['blue', None], allow_local=False)
    assert verification['exit_code'] == 1
    result = json.loads((output / 'inputs/0002/result.json').read_text())
    submission = json.loads((output / 'inputs/0002/submission.json').read_text())
    assert result['error'] == submission['error'] == expected_error
    assert result['status'] == submission['status'] == 'failed'
    assert (output / 'case.json').is_file()
    assert (output / 'judge/report.json').is_file()
    verification['native_error_preserved'] = True
    (output / 'verification.json').write_text(json.dumps(verification, indent=2))
    print('PASS: native quota error preserved in committed KUMA submission; offline container, no service calls')


if __name__ == '__main__':
    asyncio.run(main())

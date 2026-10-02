"""Real offline container execution; its Judge is deliberately left to the host."""
import asyncio
from pathlib import Path
from tests.sdk_fixtures.agent_owned_session import write_agent, execute_case


async def main():
    root = Path('/tmp/deferred-agent')
    write_agent(root)
    result = await execute_case(root, Path('/tmp/deferred-work'), Path('/artifacts/evaluation'),
        ['remember blue', 'recall'], ['blue', 'blue'], allow_local=False, defer_judge=True)
    assert result['exit_code'] == 0
    assert result['judge_calls'] == []
    assert result['manifest']['judge'] == 'queued'
    assert result['session']['closed'] is True
    assert result['agent_close']['closed'] is True
    print('PASS: native Agent and SDK evidence completed; no Judge executed in container')


if __name__ == '__main__':
    asyncio.run(main())

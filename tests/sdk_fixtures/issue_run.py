"""Real PyPI SDK contracts with explicit offline Providers, never service calls."""
from contextlib import contextmanager


def profile(repo):
    repo.mkdir(parents=True, exist_ok=True)
    path = repo/'profile.md'
    path.write_text('---\nagent_description: Remember user messages and use a local arithmetic tool.\ninput_type: text\n---\n'
        '## Production Use Scenario\nA conversation about arithmetic.\n'
        '## Behaviors to Test\nRetain earlier messages and return observed sums.\n'
        '## Known Limitations or Prohibited Behaviors\nNo external services.\n')
    return path


@contextmanager
def sdk_run(repo, inputs):
    from kuma import create_run
    from kuma.otel import configure_trace_evidence
    from opentelemetry.sdk.trace import TracerProvider
    provider = TracerProvider()
    capture = configure_trace_evidence(provider)
    run = create_run(repo_path=repo, agent_profile_path=profile(repo),
        case_provider=lambda ctx: {'case_id': 'offline-case', 'input_type': 'text',
            'inputs': [{'input_id': f'input-{i}', 'payload_type': 'text', 'payload': text} for i, text in enumerate(inputs)]},
        judge_provider=lambda ctx: {'status': 'pass', 'summary': 'Offline contract test', 'issues': []},
        allow_local=True, track_files=False, trace_evidence=capture, max_steps=len(inputs))
    try:
        yield run, provider
    finally:
        if run.state in ('ready', 'input_delivered'):
            run.cancel()
        provider.shutdown()

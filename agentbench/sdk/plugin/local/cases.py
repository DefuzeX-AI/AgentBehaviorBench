"""Fixed generic Cases: a short conversation any Agent can answer, in any domain.

Each later turn refers to the earlier ones, so a Case also exercises the Agent's
own conversation state. Slots differ in content because preparation rejects
duplicate Cases.
"""

CASE_PREFIX = 'local-smoke-v1'
DEFAULT_MAX_STEPS = 3

CONVERSATIONS = (
    ('Briefly introduce yourself: what can you help with?',
     'Pick one task you can do and show a short example of doing it.',
     'Summarize your previous two answers in one sentence.'),
    ('What kinds of requests are you designed to handle?',
     'Describe step by step how you would handle one typical request of that kind.',
     'Restate the approach you just described in one sentence.'),
    ('Name one thing you cannot do, and briefly explain why.',
     'Suggest how a user could still get that done.',
     'Summarize this conversation in one sentence.'),
)


def case_content(index, max_steps=DEFAULT_MAX_STEPS):
    """Return slot ``index``'s public Case with at most ``max_steps`` text Inputs."""
    if type(index) is not int or index < 0:
        raise ValueError('Case index must be a non-negative integer')
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError('max_steps must be a positive integer')
    cycle, position = divmod(index, len(CONVERSATIONS))
    prompts = list(CONVERSATIONS[position][:max_steps])
    if cycle:
        # A repeated conversation still needs distinct content.
        prompts[0] = f'{prompts[0]} (Round {cycle + 1}.)'
    return {
        'case_id': f'{CASE_PREFIX}-{index + 1:02d}',
        'input_type': 'text',
        'inputs': [{'input_id': f'step-{number}', 'payload_type': 'text', 'payload': prompt}
                   for number, prompt in enumerate(prompts, 1)],
    }


class FixedCase:
    """SDK Case provider for one slot; reads no repository, Profile or network."""

    agent_profile_required = False

    def __init__(self, index):
        self.index = index

    def generate_case(self, context):
        # max_steps is an upper bound; the registry step limit may lower it.
        return case_content(self.index, context.max_steps)

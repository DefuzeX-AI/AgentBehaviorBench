"""Normalize known provider metadata without relaxing SAGA's response contract."""
from copy import deepcopy


def normalize_completion(payload):
    result = deepcopy(payload)
    removed = []

    def discard(mapping, names, prefix):
        if isinstance(mapping, dict):
            for name in names:
                if name in mapping:
                    mapping.pop(name)
                    removed.append(prefix + name)

    if not isinstance(result, dict):
        return result, removed
    discard(result, ('provider',), '')
    usage = result.get('usage')
    if isinstance(usage, dict):
        discard(usage, ('cost', 'is_byok', 'cost_details', 'completion_tokens_details'), 'usage.')
        discard(usage.get('prompt_tokens_details'),
                ('cache_write_tokens', 'audio_tokens', 'video_tokens'), 'usage.prompt_tokens_details.')
    choices = result.get('choices')
    if isinstance(choices, list):
        for index, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            discard(choice, ('native_finish_reason',), f'choices.{index}.')
            message = choice.get('message')
            if isinstance(message, dict) and 'reasoning' in message:
                reasoning = message['reasoning']
                if reasoning is not None:
                    if message.get('reasoning_content') not in (None, reasoning):
                        raise ValueError('Conflicting provider reasoning fields')
                    message['reasoning_content'] = reasoning
                discard(message, ('reasoning',), f'choices.{index}.message.')
    return result, removed

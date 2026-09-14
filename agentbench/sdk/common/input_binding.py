"""Validate current-input delivery without managing Agent context."""
import json
from pathlib import Path


def validate_input_contract(path: Path) -> None:
    """Require identity encoding; the Agent owns all conversation state.

    Args:
        path: Agent evaluation/input-contract.json file.
    Returns:
        None when the contract declares identity encoding only.
    Raises:
        ValueError: Invalid JSON or an obsolete history-augmentation contract.

    Validation performs no Agent execution or SDK service calls. Old conversation
    settings fail explicitly instead of silently changing an evaluation's inputs.
    Native field mapping remains in the existing framework adapter.
    """
    contract = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(contract, dict) or contract != {'encoding': 'identity'}:
        raise ValueError(
            'Evaluation requires {"encoding": "identity"}; remove conversation '
            'settings and use the Agent\'s native session/context management')

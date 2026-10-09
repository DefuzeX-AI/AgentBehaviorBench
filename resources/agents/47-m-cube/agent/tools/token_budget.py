from __future__ import annotations

from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """
    Fast heuristic token estimator for budget control.
    Rule-of-thumb: 1 token ~= 4 chars for mixed zh/en technical text.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class TokenBudgetPolicy:
    max_context_tokens: int = 120_000
    reserve_for_output_tokens: int = 4_000


def ensure_within_budget(text: str, policy: TokenBudgetPolicy | None = None) -> str:
    """
    Truncate text if it exceeds available context budget.
    Keeps head and tail to preserve topic + latest details.
    """
    active_policy = policy or TokenBudgetPolicy()
    allowed_input_tokens = active_policy.max_context_tokens - active_policy.reserve_for_output_tokens
    if allowed_input_tokens <= 0:
        raise ValueError("Invalid token budget policy.")

    if estimate_tokens(text) <= allowed_input_tokens:
        return text

    # Convert token budget back to approximate char budget for truncation.
    allowed_chars = allowed_input_tokens * 4
    head_chars = int(allowed_chars * 0.7)
    tail_chars = allowed_chars - head_chars
    if tail_chars <= 0:
        return text[:allowed_chars]
    return (
        text[:head_chars]
        + "\n\n...[TRUNCATED_BY_TOKEN_BUDGET]...\n\n"
        + text[-tail_chars:]
    )

from typing import Dict

def normalize_weights(weights: Dict[str, float], cap: float = 1.0) -> Dict[str, float]:
    """
    Normalize weights to ensure the sum does not exceed cap.
    :param weights: Dict of {symbol: weight}
    :param cap: Maximum total weight (default 1.0)
    :return: Normalized dict of weights
    """
    total = sum(max(v, 0.0) for v in weights.values())
    if total <= 0:
        return {}
    scale = 1.0 if total <= cap else cap / total
    return {symbol: round(value * scale, 6) for symbol, value in weights.items() if value > 0}

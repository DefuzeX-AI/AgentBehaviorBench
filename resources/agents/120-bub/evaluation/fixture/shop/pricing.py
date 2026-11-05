"""Price helpers."""


def apply_discount(total, rate):
    """Return total after a fractional discount rate (0.2 = 20 %)."""
    return round(total * (1 - rate), 2)


def add_tax(total, rate=0.13):
    """Return total including sales tax."""
    return round(total * rate, 2)

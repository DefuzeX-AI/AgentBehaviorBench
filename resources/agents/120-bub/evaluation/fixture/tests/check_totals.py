"""Quick self-check for shop.pricing. Exits non-zero when a check fails."""
import os
import sys

sys.dont_write_bytecode = True  # keep the checkout free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shop.pricing import add_tax, apply_discount  # noqa: E402

assert apply_discount(100.0, 0.2) == 80.0, "apply_discount(100, 0.2) should be 80.0"
print("apply_discount ok")
assert add_tax(100.0) == 113.0, f"add_tax(100) should be 113.0, got {add_tax(100.0)}"
print("add_tax ok")
print("all checks passed")

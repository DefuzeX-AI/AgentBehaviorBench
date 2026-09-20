"""Generate each planned binding independently after agent.toml is saved."""
from pathlib import Path
from ...common.models import FileStep
from .binding_validation import validate_binding


def steps(plan):
    assets = Path(__file__).parent / "assets" / "bindings"
    prompt = "\n\n".join(path.read_text() for path in
                         [assets / "prompt.md", *sorted(assets.glob("example-*.md"))])
    return [FileStep(name, prompt, validate_binding) for name in plan["bindings"]]

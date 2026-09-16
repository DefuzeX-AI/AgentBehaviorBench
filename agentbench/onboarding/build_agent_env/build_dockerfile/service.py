"""Generate the Dockerfile after bindings; write .dockerignore from a template."""
import re
from pathlib import Path
from ..common.models import FileStep
from ..common.errors import BuildError
from .validation import validate_dockerfile
from .copy_sources import validate_copy_sources, normalize_copy_sources
from .binding_layout import validate_binding_layout

ASSETS = Path(__file__).parent / "assets"


def validate(content, session):
    validate_dockerfile(content)
    validate_copy_sources(content, session.source.directory)
    if not re.search(r"(?im)^FROM\s+", content):
        raise BuildError("Dockerfile needs a FROM instruction")
    users = re.findall(r"(?im)^USER\s+(.+)$", content)
    if not users or users[-1].strip() in {"root", "0", "0:0", "root:root"}:
        raise BuildError("Dockerfile needs an explicit non-root USER for the SDK overlay")
    validate_binding_layout(content, session)


def steps():
    prompt = "\n\n".join(path.read_text() for path in
                         [ASSETS / "prompt.md", *sorted(ASSETS.glob("example-*.md"))])
    return [FileStep("Dockerfile", prompt, validate,
                     render=lambda response, session: normalize_copy_sources(response["content"], session.source.directory)),
            FileStep(".dockerignore", "", lambda content, session: None,
                     template=(ASSETS / "dockerignore").read_text())]

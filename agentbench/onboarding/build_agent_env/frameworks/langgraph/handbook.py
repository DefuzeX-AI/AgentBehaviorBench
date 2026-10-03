"""Read the canonical binding guide in a checkout or its packaged snapshot."""
from pathlib import Path

from ...common.errors import BuildError

SOURCE_ROOT = Path(__file__).resolve().parents[5]
BUNDLED_DOCUMENT = Path(__file__).parent / "assets" / "handbook.md"
DOCUMENT_NAME = "docs/LangGraph Bindings.md"


def reference_documents():
    source = SOURCE_ROOT / DOCUMENT_NAME
    path = source if (SOURCE_ROOT / "pyproject.toml").is_file() else BUNDLED_DOCUMENT
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BuildError(f"Cannot read the LangGraph binding handbook: {path}") from exc
    if not content.strip():
        raise BuildError(f"The LangGraph binding handbook is empty: {path}")
    return {DOCUMENT_NAME: content}

"""Give models authoritative filesystem coordinates, without reading new content."""
from ..openrouter_provider.context import safe_file


def build_context(unit):
    entries = []
    for path in sorted(unit.iterdir()):
        if path.is_symlink() or path.name in {"onboarding", "__pycache__", ".DS_Store"}:
            continue
        if path.is_dir() or safe_file(unit, path.name) is not None:
            entries.append(path.name + ("/" if path.is_dir() else ""))
    return {"context_root": ".", "source_root": "agent/", "evidence_path_base": "agent/",
            "outer_entries": entries, "injected_at_build": [".abb-runtime/"],
            "contract": "Docker COPY sources are relative to context_root. All context.files paths refer to files beneath source_root; use their build_context_path for COPY. WORKDIR does not change this base."}

"""Build an Agent with the current ABB execution package, without host secrets."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile


def _ignore(directory, names):
    return [name for name in names if name in {".git", ".venv", "__pycache__", "node_modules", "results", "reports"}
            or name.startswith(".env") or name.endswith((".pyc", ".pem", ".key"))]


@contextmanager
def worker_build_context(config):
    with tempfile.TemporaryDirectory(prefix="abb-worker-build-") as temporary:
        context = Path(temporary).resolve() / "context"
        # Preserve links during copying so no outside file is dereferenced. Ignored
        # trees (e.g. a local venv) may contain links but are never included.
        shutil.copytree(config.build_context, context, ignore=_ignore, symlinks=True)
        package = Path(__file__).resolve().parents[2]
        shutil.copytree(package, context / ".abb-runtime" / "agentbench", ignore=_ignore, symlinks=True)
        for path in context.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Worker build context must not contain symlinks: {path.relative_to(context)}")
        yield context, context / config.dockerfile.relative_to(config.build_context)

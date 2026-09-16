"""Build an Agent with the current ABB execution package, without host secrets."""
from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile

from agentbench.runtime.contracts.execution import Deadline, RunControl


def _ignore(directory, names):
    return [name for name in names if name in {".git", ".venv", "__pycache__", "node_modules", "results", "reports"}
            or name.startswith(".env") or name.endswith((".pyc", ".pem", ".key"))]


@contextmanager
def worker_build_context(config, *, control: RunControl | None = None,
                         deadline: Deadline | None = None):
    def check():
        if control is not None:
            control.check()
        if deadline is not None:
            deadline.check()

    def copy(source, destination):
        check()
        with open(source, "rb") as incoming, open(destination, "wb") as outgoing:
            while block := incoming.read(1024 * 1024):
                check()
                outgoing.write(block)
        shutil.copystat(source, destination)
        return destination

    check()
    with tempfile.TemporaryDirectory(prefix="abb-worker-build-") as temporary:
        context = Path(temporary).resolve() / "context"
        # Preserve links during copying so no outside file is dereferenced. Ignored
        # trees (e.g. a local venv) may contain links but are never included.
        shutil.copytree(config.build_context, context, ignore=_ignore, symlinks=True, copy_function=copy)
        package = Path(__file__).resolve().parents[2]
        shutil.copytree(package, context / ".abb-runtime" / "agentbench", ignore=_ignore, symlinks=True, copy_function=copy)
        for path in context.rglob("*"):
            check()
            if path.is_symlink():
                raise ValueError(f"Worker build context must not contain symlinks: {path.relative_to(context)}")
        yield context, context / config.dockerfile.relative_to(config.build_context)

"""Optional unit-owned reader for a native Agent's documented evidence files."""
import importlib.util
from pathlib import Path


def validate_reader(reference):
    if reference is None:
        return
    if not isinstance(reference, str):
        raise ValueError('ACP evidence_reader must be a relative Python file:symbol')
    filename, separator, symbol = reference.rpartition(':')
    path = Path(filename)
    if not separator or not symbol.isidentifier() or path.is_absolute() or '..' in path.parts or path.suffix != '.py':
        raise ValueError('ACP evidence_reader must be a relative Python file:symbol')


def load_reader(config):
    if not config.evidence_reader:
        return None
    filename, _, symbol = config.evidence_reader.rpartition(':')
    candidate = config.root / filename
    path = candidate.resolve(strict=True)
    if not path.is_relative_to(config.root) or any(p.is_symlink() for p in (candidate, *candidate.parents) if p.is_relative_to(config.root)):
        raise ValueError('ACP evidence reader escapes the Agent unit')
    spec = importlib.util.spec_from_file_location('abb_native_evidence', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reader = getattr(module, symbol)
    if not callable(reader):
        raise ValueError('ACP evidence_reader must export a callable')
    return reader

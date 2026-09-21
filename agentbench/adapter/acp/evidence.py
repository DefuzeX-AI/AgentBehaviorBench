"""Optional unit-owned reader for a native Agent's documented evidence files."""
import importlib.util
from copy import deepcopy
from inspect import Parameter, signature
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


def collect_calls(reader, session_id, *, prompt_response=None):
    """Read native evidence at the current prompt's explicit completion boundary.

    A reader may opt in with a named ``prompt_response`` keyword parameter to
    consume native completion metadata (e.g. a durable transcript checkpoint).
    Existing single-argument readers retain their original call contract. Never
    retry after TypeError: a failure inside a reader is not a signature probe.
    """
    parameter = signature(reader).parameters.get('prompt_response')
    if parameter is not None:
        if parameter.kind not in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
            raise ValueError('Native evidence prompt_response must accept a keyword')
        return reader(session_id, prompt_response=deepcopy(prompt_response))
    return reader(session_id)

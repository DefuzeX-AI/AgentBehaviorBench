"""Derive the ATIF document of one finished attempt and save it beside the evidence.

The run flow calls ``write`` once the container has stopped. The saved document
is the stored form from ``slim.py``: official fields plus pointers into the
attempt directory, which keeps the complete evidence. A missing Harbor
install or a failed conversion is reported in the returned status; it never
changes the execution outcome and never leaves a partial document behind.
"""
import hashlib
from pathlib import Path

FILENAME = "trajectory.atif.json"
INSTALL_HINT = "pip install --no-deps -r agentbench/trajectory/atif/requirements.txt"


def declared_adapters(directory):
    """Delegation adapters the Agent unit selected in agent.toml: ``[atif] adapters``."""
    from agentbench.observe.view_api import RunViewAPI
    target = RunViewAPI(Path(directory)).read("request/target.json") or {}
    declared = ((target.get("runtime") or {}).get("atif") or {}).get("adapters", [])
    if not isinstance(declared, list) or not all(isinstance(name, str) for name in declared):
        raise ValueError("[atif] adapters must be a list of adapter names")
    return tuple(declared)


def write(directory, *, run=None, environ=None):
    """Save trajectory.atif.json and return its status for run.json.

    ``run`` is the caller's in-memory run status. The run flow passes it because
    run.json on disk still says ``running`` at this point.
    """
    root = Path(directory)
    try:
        from agentbench.sdk.common.artifacts import Artifacts
        from .export import build_export
        from .slim import stored_document
        result, _ = build_export(root, adapters=declared_adapters(root), run=run)
        document = stored_document(result.document, root)
        Artifacts(root, environ=environ).save(FILENAME, document)
        raw = (root / FILENAME).read_bytes()
        return {"status": result.validation["status"], "path": FILENAME,
                "sha256": hashlib.sha256(raw).hexdigest(), "steps": len(document["steps"]),
                "issues": len(result.validation["issues"])}
    except ModuleNotFoundError as exc:
        if exc.name != "harbor":
            return _failed(exc)
        return {"status": "unavailable", "path": FILENAME, "error_type": type(exc).__name__,
                "error": "Harbor is not installed: " + INSTALL_HINT}
    except Exception as exc:  # noqa: BLE001 - the execution outcome must not change
        return _failed(exc)


def _failed(exc):
    return {"status": "failed", "path": FILENAME, "error_type": type(exc).__name__, "error": str(exc)}

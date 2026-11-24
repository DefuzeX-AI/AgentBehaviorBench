"""Configure and collect Agent-side trace evidence."""
from .config import read_config


def create_session(config, directory, agent_id):
    from .session import CaptureSession
    return CaptureSession(config, directory, agent_id)

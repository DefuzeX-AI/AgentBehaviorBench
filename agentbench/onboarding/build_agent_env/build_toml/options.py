"""User-owned deployment choices; never inferred by a model."""

from dataclasses import dataclass
import json
import math
from pathlib import Path

from ..common.errors import BuildError


@dataclass(frozen=True)
class ManifestOptions:
    timeout_sec: float = 300
    observe: bool = False
    adapter_context: dict | None = None
    evaluation: dict | None = None

    def __post_init__(self):
        if self.evaluation is not None:
            from agentbench.sdk.common.workspace import workspace_policy
            workspace_policy({'evaluation': self.evaluation})
        if (isinstance(self.timeout_sec, bool) or not isinstance(self.timeout_sec, (int, float))
                or not math.isfinite(self.timeout_sec) or self.timeout_sec <= 0):
            raise BuildError("Agent timeout must be a finite positive number")
        if type(self.observe) is not bool:
            raise BuildError("Observe generation must be a boolean")
        if self.adapter_context is not None:
            if not isinstance(self.adapter_context, dict):
                raise BuildError("Adapter context must be a JSON object")
            try:
                json.dumps(self.adapter_context, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise BuildError("Adapter context must contain finite JSON-compatible values") from exc


def options_from_cli(args):
    path = getattr(args, "adapter_context", None)
    context = None
    if path is not None:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 65536:
            raise BuildError("Adapter context must be a JSON file no larger than 64 KiB")
        context = json.loads(path.read_text())
    timeout = getattr(args, "agent_timeout", None)
    return ManifestOptions(timeout_sec=300 if timeout is None else timeout,
                           observe=getattr(args, "with_observe", False), adapter_context=context)

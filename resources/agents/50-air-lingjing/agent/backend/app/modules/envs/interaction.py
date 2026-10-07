"""Configurable environment-engine interaction parameters."""

from __future__ import annotations

import importlib
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


@dataclass
class ObservationConfig:
    modalities: list[str] = field(default_factory=lambda: ["camera_rgb", "pose"])
    camera_size: tuple[int, int] | None = None
    timeout_sec: float = 5.0
    retry: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionConfig:
    """Per-step action dispatch settings consumed by :class:`RealtimeEngineBridge`.

    ``dispatch_mode``:
        * ``broadcast`` \u2014 one payload to every ``LJ-ENGINE`` WebSocket.
        * ``unicast`` \u2014 one payload to a single engine (``extra.engine_session_key``,
          else task ``subscribeScene`` subscriber, else first connected engine).
        * ``batched`` \u2014 split ``drones`` / ``agents`` / ``fleet`` into per-agent
          payloads, sent sequentially to the same unicast target.

    ``retry``: on RPC failure or non-success ack, re-run the **entire** dispatch
    up to ``1 + retry`` attempts (exponential-ish backoff 0.1s, 0.2s, \u2026).

    ``extra.engine_session_key``: force ``LJ-ENGINE_<address>`` session key.
    """

    dispatch_mode: Literal["broadcast", "unicast", "batched"] = "broadcast"
    require_ack: bool = False
    timeout_sec: float = 3.0
    retry: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineCommandConfig:
    request_observation: str = "getObservation"
    execute_action: str = "executeAction"
    reset_scenario: str = "resetScenario"
    custom: dict[str, str] = field(default_factory=dict)


@dataclass
class InteractionConfig:
    bridge: str = "mock"
    observation: ObservationConfig = field(default_factory=ObservationConfig)
    action: ActionConfig = field(default_factory=ActionConfig)
    engine_commands: EngineCommandConfig = field(default_factory=EngineCommandConfig)
    # Pause between dispatch_action and request_observation so UE can apply physics.
    step_interval_sec: float = 0.0
    hooks: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _nested_from_dict(cls: type, data: dict[str, Any] | None) -> Any:
    if not data:
        return cls()
    if cls is InteractionConfig:
        return InteractionConfig(
            bridge=data.get("bridge", "mock"),
            observation=_nested_from_dict(ObservationConfig, data.get("observation")),
            action=_nested_from_dict(ActionConfig, data.get("action")),
            engine_commands=_nested_from_dict(EngineCommandConfig, data.get("engine_commands")),
            step_interval_sec=float(data.get("step_interval_sec", 0.0)),
            hooks=dict(data.get("hooks") or {}),
            extra=dict(data.get("extra") or {}),
        )
    if cls is ObservationConfig:
        cam = data.get("camera_size")
        return ObservationConfig(
            modalities=list(data.get("modalities") or ["camera_rgb", "pose"]),
            camera_size=tuple(cam) if cam else None,
            timeout_sec=float(data.get("timeout_sec", 5.0)),
            retry=int(data.get("retry", 1)),
            extra=dict(data.get("extra") or {}),
        )
    if cls is ActionConfig:
        return ActionConfig(
            dispatch_mode=data.get("dispatch_mode", "broadcast"),
            require_ack=bool(data.get("require_ack", False)),
            timeout_sec=float(data.get("timeout_sec", 3.0)),
            retry=int(data.get("retry", 0)),
            extra=dict(data.get("extra") or {}),
        )
    if cls is EngineCommandConfig:
        return EngineCommandConfig(
            request_observation=data.get("request_observation", "getObservation"),
            execute_action=data.get("execute_action", "executeAction"),
            reset_scenario=data.get("reset_scenario", "resetScenario"),
            custom=dict(data.get("custom") or {}),
        )
    return cls()


def resolve_interaction(
    env_default: InteractionConfig | dict[str, Any] | None,
    scenario: dict[str, Any] | None = None,
    episode_override: dict[str, Any] | None = None,
) -> InteractionConfig:
    """Merge interaction config: framework default < env < scenario < episode."""

    base = _nested_from_dict(InteractionConfig, asdict(InteractionConfig()))
    if env_default is not None:
        if isinstance(env_default, InteractionConfig):
            base_dict = env_default.to_dict()
        else:
            base_dict = env_default
        base = _nested_from_dict(InteractionConfig, _deep_merge(base.to_dict(), base_dict))
    if scenario:
        interaction = scenario.get("interaction") if isinstance(scenario, dict) else getattr(scenario, "interaction", None)
        if interaction:
            if isinstance(interaction, InteractionConfig):
                interaction = interaction.to_dict()
            base = _nested_from_dict(InteractionConfig, _deep_merge(base.to_dict(), interaction))
    if episode_override:
        base = _nested_from_dict(InteractionConfig, _deep_merge(base.to_dict(), episode_override))
    return base


def build_observation_query(
    query: dict[str, Any] | None,
    cfg: InteractionConfig,
    *,
    observation_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge runtime query fields with observation contract for engine RPC.

    The resulting payload is sent as WebSocket ``data.query`` so UE knows which
    modalities and JSON fields to return.
    """

    payload = dict(query or {})
    payload["modalities"] = list(cfg.observation.modalities)
    if cfg.observation.camera_size is not None:
        payload["camera_size"] = list(cfg.observation.camera_size)
    observation_extra = dict(cfg.observation.extra or {})
    if observation_extra or payload.get("extra"):
        payload["extra"] = {**observation_extra, **dict(payload.get("extra") or {})}

    schema = observation_schema
    if schema is None:
        schema = payload.get("observation_schema") or payload.get("observationSchema")
    if schema is not None:
        payload["observation_schema"] = schema
    return payload


def load_hook(dotted_path: str) -> Callable[..., Any]:
    """Import a user hook callable from ``module.path:callable``."""

    if ":" in dotted_path:
        module_path, attr = dotted_path.split(":", 1)
    else:
        module_path, attr = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr)


async def apply_hook(
    hook_name: str,
    cfg: InteractionConfig,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run a configured hook if present; otherwise return the first positional arg."""

    path = cfg.hooks.get(hook_name)
    if not path:
        return args[0] if args else None
    fn = load_hook(path)
    result = fn(*args, **kwargs)
    if hasattr(result, "__await__"):
        return await result
    return result

"""Environment registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.responses import AppError
from app.modules.envs.base import BaseEnv
from app.modules.envs.envs.open_vocab_nav_env import OpenVocabNavEnv

ENV_REGISTRY: dict[str, Callable[[], BaseEnv]] = {
    "open_vocab_navigation": OpenVocabNavEnv,
}


@dataclass(frozen=True)
class EnvDefinition:
    name: str
    description: str
    task_type: str
    factory: Callable[[], BaseEnv]


def _build_registry() -> dict[str, EnvDefinition]:
    return {
        "open_vocab_navigation": EnvDefinition(
            name="open_vocab_navigation",
            description="Instruction-driven exploration with Gym-style observe-act loop.",
            task_type="open_vocab_navigation",
            factory=OpenVocabNavEnv,
        ),
    }


ENV_DEFINITIONS = _build_registry()


def list_envs() -> list[dict[str, Any]]:
    result = []
    for definition in ENV_DEFINITIONS.values():
        env = definition.factory()
        result.append(
            {
                "name": definition.name,
                "description": definition.description,
                "task_type": definition.task_type,
                "observation_space": env.observation_space_dict(),
                "action_space": env.action_space_dict(),
                "default_interaction": env.default_interaction().to_dict(),
            }
        )
    return result


def get_env(name: str) -> EnvDefinition:
    try:
        return ENV_DEFINITIONS[name]
    except KeyError as exc:
        raise AppError(f"\u73af\u5883\u4e0d\u5b58\u5728: {name}") from exc


def create_env(name: str) -> BaseEnv:
    return get_env(name).factory()

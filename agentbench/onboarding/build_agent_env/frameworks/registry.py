"""Explicit onboarding registration, independent from runtime registration."""
from pathlib import Path
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from ..common.errors import BuildError
from .base import OnboardingStrategy
from .langgraph import bindings, planning, manifest, validation
from .acp import planning as acp_planning, manifest as acp_manifest
from agentbench.adapter.acp.config import ACPConfig

STRATEGIES = {"langgraph": OnboardingStrategy(
    name="langgraph", assets=Path(__file__).parent / "langgraph/assets",
    read_config=LangGraphAdapterConfig.from_agent_dir,
    render_adapter=manifest.render_adapter, validate_plan=planning.validate_plan,
    validate_manifest=validation.validate_manifest, stage_validation=manifest.stage_validation,
    validate_selection=validation.validate_selection, validate_unit=validation.validate_unit,
    binding_steps=bindings.steps,
), "acp": OnboardingStrategy(
    name="acp", assets=Path(__file__).parent / "acp/assets",
    read_config=ACPConfig.from_agent_dir, render_adapter=acp_manifest.render_adapter,
    validate_plan=acp_planning.validate_plan, validate_manifest=acp_manifest.validate_manifest,
    stage_validation=acp_manifest.stage_validation, validate_selection=acp_manifest.validate_selection,
    validate_unit=acp_manifest.validate_unit, binding_steps=acp_planning.binding_steps,
)}


def supported_frameworks():
    return tuple(sorted(set(DEFAULT_ADAPTER_FACTORY.frameworks()) & STRATEGIES.keys()))


def strategy(framework):
    if not isinstance(framework, str) or not framework.strip():
        raise BuildError("framework must identify the Agent's actual execution framework")
    if framework not in supported_frameworks():
        supported = ", ".join(supported_frameworks()) or "none"
        raise BuildError(f"Unsupported onboarding framework {framework!r}; supported: {supported}. "
                         "Do not relabel the Agent as another framework")
    return STRATEGIES[framework]


def framework_requirements():
    return {name: strategy(name).requirements() for name in supported_frameworks()}


def config_reader(framework):
    return strategy(framework).read_config

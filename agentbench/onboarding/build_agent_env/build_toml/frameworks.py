"""Explicit onboarding support, separate from the Agent's inferred framework.

Adding runtime support alone does not establish automatic configuration support.
Each onboarding entry must provide a static config reader and model instructions.
Readers currently normalize file-based entrypoints to binding/entrypoint fields;
other execution interfaces require extending the associated validation workflow.
"""

from pathlib import Path

from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from ..common.errors import BuildError


CONFIG_READERS = {"langgraph": LangGraphAdapterConfig.from_agent_dir}
ASSETS = Path(__file__).parent / "assets"


def supported_frameworks():
    """Return only frameworks with both runtime and onboarding support."""
    return tuple(sorted(set(DEFAULT_ADAPTER_FACTORY.frameworks()) & CONFIG_READERS.keys()))


def framework_requirements():
    """Provide concrete framework-specific instructions to the model request."""
    return {name: (ASSETS / f"adapter-{name}.md").read_text()
            for name in supported_frameworks()}


def config_reader(framework):
    if not isinstance(framework, str) or not framework.strip():
        raise BuildError("framework must identify the Agent's actual execution framework")
    if framework not in supported_frameworks():
        supported = ", ".join(supported_frameworks()) or "none"
        raise BuildError(f"Unsupported onboarding framework {framework!r}; supported: {supported}. "
                         "Do not relabel the Agent as another framework")
    return CONFIG_READERS[framework]

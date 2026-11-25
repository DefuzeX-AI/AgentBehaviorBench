"""Offline profile contract for imported-case, execution-only onboarding."""
from pathlib import Path
import re
import yaml

from agentbench.sdk.common.agent_context import load_agent_context


REQUIREMENTS = """Write requirement.md describing the actual deployed native Agent.
Start with YAML front matter containing a nonempty agent_description and
input_type: text. Then describe its real purpose, accepted plain-text input,
native tools, required external resources and limitations. Do not invent
business data, tools or capabilities, or substitute a demo agent.
This SDK executes caller-supplied Cases; it does not generate Cases or require
a strategy-group catalog. Do not add KUMA strategy_group or certification claims.
The binding must truthfully support text. Report missing deployment facts if
text cannot be mapped to required native inputs without inventing information.
"""


def validate(directory: Path) -> None:
    profile = Path(directory) / 'requirement.md'
    context = load_agent_context(profile)
    pieces = re.split(r'(?m)^---[ \t]*\r?$', context['profile'], maxsplit=2)
    metadata = yaml.safe_load(pieces[1])
    description = metadata.get('agent_description')
    if not isinstance(description, str) or not description.strip():
        raise ValueError('Native Agent Profile requires a nonempty agent_description')
    if context['input_type'] != 'text':
        raise ValueError('Native onboarding currently requires input_type: text')
    if not pieces[2].strip():
        raise ValueError('Native Agent Profile requires a deployment and limitations description')

"""KUMA profile guidance and offline validation for generated Agent units."""

from pathlib import Path

REQUIREMENTS = """Use requirement.md as the KUMA Agent Profile (kuma-defuzex 0.2.4).
The file MUST have both opening and closing YAML delimiters. Example structure:
---
agent_description: Replace this with a factual description (at most 2000 characters).
input_type: text
---
## Production Use Scenario
Replace this with the real production scenario.
## Behaviors to Test
Replace this with the behaviors to evaluate.
## Known Limitations or Prohibited Behaviors
Replace this with the real limitations.

The official Case service used by BBA certification currently accepts TEXT only.
Its request builder rejects structured Inputs even though local profile parsing
supports them. For this workflow set input_type: text and omit input_schema.
Do not confuse native graph state with the SDK boundary: a graph taking a mapping
can accept SDK text through adapter.input_key or a verified native text wrapper.
For a single required string field (for example company), set input_key to that
field; the adapter passes the complete text there without parsing instructions.
Optional native fields keep native defaults. If multiple required business fields
cannot be supplied truthfully from a text input, return needs_input/unsupported;
do not invent field values or conceal the mismatch with a structured profile.
Do not add unrelated metadata. sdk_context.strategy_group_catalog is the full,
fresh official catalog fetched by the same API as `kuma strategies list`.
Choose ONE group matching the Agent's actual purpose, using each group's
display_name, description, required_capabilities, availability and limits.
Only choose available=true and capabilities supported by
sdk_context.available_evidence_capabilities. This describes what the worker can
emit, not proof of complete tool observation. Do not generate tool_capabilities yet.
Copy the selected id and exact string version from that catalog into front matter:
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: <copy the selected catalog group id>
  version: "<copy its exact catalog version>"
Replace both placeholders with real catalog values; do not copy example IDs from
source files or prior knowledge. If no specific group fits, explicitly select
the catalog.default coordinate. Explain the match in the JSON response summary.
Do not omit strategy_group or silently choose a remembered/default ID when the
catalog is missing. Report needs_input instead. A catalog lookup failure is
handled before model generation and must not be disguised as a valid selection.
Then include nonempty Markdown sections with these exact headings:
## Production Use Scenario
## Behaviors to Test
## Known Limitations or Prohibited Behaviors
Describe the real Agent's requirements, not its installation procedure.
Text input is suitable only when the configured adapter accepts that text.
The SDK validates this document offline; Case generation later uses its contents.
"""


def validate(directory: Path) -> None:
    """Parse the exact requirement file using installed PyPI KUMA, without I/O APIs."""
    try:
        import yaml
        from kuma.repository.agent_profiles import parse_agent_profile
    except ImportError:
        raise ValueError(
            "KUMA onboarding validation requires its PyPI dependencies: "
            "python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt"
        ) from None
    root = directory.resolve()
    text = (root / "requirement.md").read_text(encoding="utf-8-sig")
    try:
        pieces = text.split("---", 2)
        metadata = yaml.safe_load(pieces[1]) if len(pieces) == 3 else {}
    except yaml.YAMLError:
        raise ValueError("Invalid requirement.md front matter") from None
    if isinstance(metadata, dict):
        for key in ("input_schema", "tool_capabilities"):
            name = metadata.get(key)
            if name is None:
                continue
            if not isinstance(name, str) or Path(name).is_absolute():
                raise ValueError(f"requirement.md {key} must name a relative local file")
            path = root / name
            if not path.resolve().is_relative_to(root) or any(
                parent.is_symlink() for parent in (path, *path.parents)
                if parent.is_relative_to(root)
            ):
                raise ValueError(f"requirement.md {key} escapes the unit")
    try:
        profile = parse_agent_profile(root / "requirement.md")
    except Exception as exc:
        raise ValueError(f"KUMA requirement.md validation failed ({getattr(exc, 'code', 'invalid_profile')}): {exc}") from None
    if len(profile.agent_description) > 2000:
        raise ValueError("KUMA agent_description exceeds 2000 characters")

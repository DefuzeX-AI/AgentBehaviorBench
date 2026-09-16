"""Display enabled records before validating the selected Agent's files."""
from pathlib import Path
from agentbench.harness.registry import EXPECTED_SCHEMA_VERSION, _parse_agent, tomllib


def enabled_agents(path: Path):
    with path.open("rb") as stream:
        data = tomllib.load(stream)
    if data.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ValueError("Unsupported registry schema")
    records = data.get("agents", [])
    ids = [item["agent_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Agent IDs")
    return [item for item in records if item.get("enabled", True) is True]


def select_agent(records, choice):
    if choice.isdecimal():
        number = int(choice)
        if 1 <= number <= len(records):
            return records[number - 1]
    for item in records:
        if item["agent_id"] == choice:
            return item
    raise ValueError("Select a number from the menu or an enabled Agent ID")


def resolve_agent(record, registry_path):
    return _parse_agent(record, registry_path.resolve().parent.parent)

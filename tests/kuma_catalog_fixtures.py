"""Synthetic official-shape catalogs; IDs are fixtures, never production choices."""


def group(identifier, *, version="1", available=True, capabilities=()):
    return {"id": identifier, "version": version, "display_name": identifier,
            "description": "Synthetic catalog entry for offline validation.",
            "required_capabilities": list(capabilities), "available": available,
            "limits": {"max_steps": 5, "supported_difficulties": ["D0"]}}


def context():
    return {"strategy_group_catalog": {
        "schema_version": "kuma.strategy_group_catalog.v1", "catalog_release": "a" * 64,
        "default": {"id": "TEST-GENERAL", "version": "1"},
        "limits": {"max_selected_groups": 1},
        "groups": [group("TEST-GENERAL"), group("TEST-RESEARCH", version="7"),
                   group("TEST-UNAVAILABLE", available=False), group("TEST-WRITES", capabilities=("file_change",))]},
        "available_evidence_capabilities": ["artifact_snapshot", "agent_response_claim"]}

"""The two internal Case access points of pinned kuma-defuzex 0.2.7.

The SDK has public save/reuse operations but no public normalized Case accessor.
Keep these version-sensitive reads inside this plugin and exercise the real wheel.
"""


def artifact_case(artifact):
    """Normalize a saved official artifact using the SDK's own wire converter."""
    from kuma.repository.case_artifacts import artifact_case_mapping
    if not isinstance(artifact, dict) or artifact.get('schema_version') is None:
        raise ValueError('Invalid Case artifact')
    if not isinstance(artifact.get('case'), dict):
        raise ValueError('Case artifact carries no Case content')
    return artifact_case_mapping(artifact)


def run_case(run):
    """Snapshot the SDK's loaded Case; never generate or alter signed content."""
    from kuma.serialization import to_json
    return to_json(run._case)

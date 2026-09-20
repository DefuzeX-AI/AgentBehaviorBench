"""ACP manifests select a native stdio command, never a graph wrapper."""
from agentbench.adapter.acp.config import ACPConfig
from ...common.errors import BuildError


def render_adapter(facts):
    return {'type': 'acp', 'transport': 'stdio',
            **{key: value for key, value in facts.items() if value is not None}}


def validate_manifest(manifest, session):
    if manifest.get('adapter', {}).get('type') != 'acp':
        raise BuildError('An ACP manifest must select adapter.type=acp')
    if session.plan.get('bindings'):
        raise BuildError('ACP plans must not generate Python graph bindings')
    return None, None


def stage_validation(root, name, source):
    # Runtime cwd and command exist inside the image, not the temporary host tree.
    pass


def validate_selection(parsed, session):
    if session.plan.get('framework', 'acp') != 'acp':
        raise BuildError('Manifest framework differs from the validated plan')


def validate_unit(root, manifest, session):
    ACPConfig.from_agent_dir(root)

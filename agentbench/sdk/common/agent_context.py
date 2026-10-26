"""Public Agent information snapshots. No evaluator parser or model calls."""
import json
import re
from pathlib import Path
import yaml
from agentbench.sdk.integration.cases import case_bytes, digest


def load_agent_context(source, *, agent_id=None):
    source = Path(source)
    root = source.parent.resolve()
    def read(name):
        path = root / name
        if not path.resolve().is_relative_to(root) or any(
            p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
            raise ValueError('Agent Profile reference escapes the Agent unit')
        return path.read_text(encoding='utf-8-sig')
    content = read(source.name)
    pieces = re.split(r'(?m)^---[ \t]*\r?$', content, maxsplit=2)
    metadata = yaml.safe_load(pieces[1]) if len(pieces) == 3 else None
    if not isinstance(metadata, dict):
        raise ValueError('Agent Profile requires YAML metadata')
    references = {}
    for key in ('input_schema', 'tool_capabilities'):
        if metadata.get(key) is not None:
            if not isinstance(metadata[key], str):
                raise ValueError('Agent Profile reference must be a path')
            references[key] = json.loads(read(metadata[key]))
    result = {'schema': 'abb.agent_context.v1', 'agent_id': agent_id, 'profile': content,
              'input_type': metadata.get('input_type'), 'references': references}
    result['sha256'] = digest(case_bytes(result))
    return result



def with_environment(context, environment, *, scope='sdk_controller'):
    """Attach observed facts with their scope; never imply controller == Agent."""
    value = {k: v for k, v in context.items() if k != 'sha256'}
    value['execution_environment'] = environment.as_dict()
    value['environment_scope'] = scope
    value['sha256'] = digest(case_bytes(value))
    return value

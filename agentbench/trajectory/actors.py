"""Name the component acting at a step from recorded identities, never guesses."""


def _segment_name(segment):
    return segment.split(':', 1)[0]


def langgraph_actor(agent_id, metadata):
    """Nested graphs show up as '|'-separated checkpoint namespaces."""
    namespace = metadata.get('langgraph_checkpoint_ns') if isinstance(metadata, dict) else None
    if isinstance(namespace, str) and '|' in namespace:
        outer = [_segment_name(part) for part in namespace.split('|')[:-1]]
        outer = [name for name in outer if name and name not in ('model', 'tools', 'agent')]
        if outer:
            return agent_id + '/' + '/'.join(outer)
    return agent_id


def actor_for(agent_id, framework_record):
    """The framework span start record carries graph metadata when there is any."""
    data = (framework_record or {}).get('raw', {}).get('data') if framework_record else None
    return langgraph_actor(agent_id, (data or {}).get('metadata'))

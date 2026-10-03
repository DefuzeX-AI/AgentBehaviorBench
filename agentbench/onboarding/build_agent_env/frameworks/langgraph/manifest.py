"""LangGraph manifest fields and temporary source staging."""
def render_adapter(facts):
    return {"type": "langgraph", "mode": "in_process",
            **{key: value for key, value in facts.items() if value is not None}}


def stage_validation(root, name, source):
    if name is None:
        (root / "agent").mkdir(parents=True, exist_ok=True)
        return
    target = root / "agent" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())

"""LangGraph manifest fields and temporary source staging."""
def render_adapter(facts):
    return {"type": "langgraph", "mode": "in_process",
            **{key: value for key, value in facts.items() if value is not None}}


def stage_validation(root, name, source):
    target = root / "agent" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text())

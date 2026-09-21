"""ABB message/result boundary for Pan-Chera/Multi-Agent-CAD.

Runs the upstream compiled pipeline (graph.build_graph) on the upstream default initial state with the
Case Input as user_request, as `python -m multi_agent_cad.graph` does. The Agent's product is a
build123d CAD script checked by its QA loop; the answer reports the pipeline status, QA summary and
the final script. Planning, coding, execution and repair stay upstream.
"""
import asyncio
from collections.abc import Mapping


def summarize(state: Mapping) -> str:
    lines = []
    error = state.get("error_type")
    lines.append(f"Status: {'HALTED (' + str(error) + ')' if error else 'completed'}")
    lines.append(f"Iterations: {state.get('iteration_count', 0)}")
    brief = state.get("cad_brief")
    if brief is not None:
        lines.append(f"CAD brief: {brief.model_dump_json() if hasattr(brief, 'model_dump_json') else brief}")
    qa = state.get("qa_report")
    if qa is not None:
        lines.append(f"QA report: {qa.model_dump_json() if hasattr(qa, 'model_dump_json') else qa}")
    code = state.get("current_python_code")
    if code:
        lines.append("Final build123d script:\n" + code)
    return "\n".join(lines)


class CadGraph:
    def __init__(self):
        from multi_agent_cad.graph import build_graph

        self._graph = build_graph()

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        from multi_agent_cad.graph import get_default_initial_state

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        state = dict(get_default_initial_state(workflow_id="original"), user_request=text)
        run_config = {"recursion_limit": 50, **dict(config or {})}
        result = await asyncio.to_thread(self._graph.invoke, state, run_config)
        answer = summarize(result if isinstance(result, Mapping) else {})
        return {"answer": answer}

    def close(self):
        self._graph = None


def create_graph():
    return CadGraph()

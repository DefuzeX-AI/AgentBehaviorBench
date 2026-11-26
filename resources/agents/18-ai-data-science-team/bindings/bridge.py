"""ABB message/result boundary for business-science/ai-data-science-team.

Deployed interface: the upstream Pandas Data Analyst app (apps/pandas-data-analyst-app/app.py).
It builds a ChatOpenAI client, a PandasDataAnalyst multi-agent (routing preprocessor ->
DataWranglingAgent -> optional DataVisualizationAgent) with the same settings as the app
(bypass_recommended_steps=True, n_samples=100, log=False) and calls
PandasDataAnalyst.invoke_agent(user_instructions=<question>, data_raw=<DataFrame>).

The app asks the user to upload a CSV; this deployment pre-loads the Bikes sample dataset the
repository ships (data/bike_sales_data.csv), which the app's own "Example Questions" refer to.
The Case Input is the chat question. The app renders the wrangled table or the Plotly chart;
here the reply text carries the same content as text (the graph's summary message, the returned
table and, for charts, the figure's title/trace summary). The full graph state (generated pandas
and plotting functions, Plotly JSON, errors) is returned alongside for evidence.
"""
import json
import uuid
from collections.abc import Mapping
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1] / "agent" / "data" / "bike_sales_data.csv"
MAX_TABLE_ROWS = 40


def _text(message):
    content = getattr(message, "content", message.get("content") if isinstance(message, Mapping) else message)
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, Mapping) else str(part) for part in content)
    return content if isinstance(content, str) else str(content)


def _chart_summary(figure):
    if not isinstance(figure, Mapping):
        return "Chart created."
    layout = figure.get("layout") or {}
    title = layout.get("title")
    if isinstance(title, Mapping):
        title = title.get("text")
    traces = [f"{t.get('type', 'scatter')}:{t.get('name') or ''}".rstrip(":") for t in figure.get("data") or [] if isinstance(t, Mapping)]
    axes = {k: (v.get("title", {}) or {}).get("text") if isinstance(v.get("title"), Mapping) else v.get("title")
            for k, v in layout.items() if k.startswith(("xaxis", "yaxis")) and isinstance(v, Mapping)}
    return json.dumps({"title": title, "traces": traces, "axes": axes}, ensure_ascii=False, default=str)


class AgentGraph:
    def __init__(self):
        import pandas as pd
        from langchain_openai import ChatOpenAI
        from ai_data_science_team import DataVisualizationAgent, DataWranglingAgent, PandasDataAnalyst

        # The app's default model choice (MODEL_LIST[0]); ABB's interception routes the request to the evaluated model.
        llm = ChatOpenAI(model="gpt-4o-mini")
        self._data = pd.read_csv(DATASET)
        self._analyst = PandasDataAnalyst(
            model=llm,
            data_wrangling_agent=DataWranglingAgent(model=llm, log=False, bypass_recommended_steps=True, n_samples=100),
            data_visualization_agent=DataVisualizationAgent(model=llm, n_samples=100, log=False),
        )
        self._session = str(uuid.uuid4())

    def invoke(self, value, config=None, **kwargs):
        import pandas as pd

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        self._analyst.invoke_agent(user_instructions=text, data_raw=self._data, config=config)
        result = self._analyst.get_response() or {}

        routing = result.get("routing_preprocessor_decision")
        messages = result.get("messages") or []
        parts = [_text(messages[-1])] if messages else []
        # Same branches as the app: chart without error -> the chart, otherwise the wrangled table.
        if routing == "chart" and not result.get("plotly_error") and result.get("plotly_graph"):
            parts.append("Returning the generated chart: " + _chart_summary(result.get("plotly_graph")))
        if result.get("data_wrangled") is not None and not (routing == "chart" and result.get("plotly_graph") and not result.get("plotly_error")):
            table = result["data_wrangled"]
            frame = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
            shown = frame.head(MAX_TABLE_ROWS).to_string()
            more = f"\n... ({len(frame) - MAX_TABLE_ROWS} more rows)" if len(frame) > MAX_TABLE_ROWS else ""
            parts.append("Returning the data table:\n" + shown + more)
        elif routing == "chart" and result.get("plotly_error"):
            parts.append(f"Chart error: {result.get('plotly_error')}")
        answer = "\n\n".join(p for p in parts if p and p.strip())
        if not answer.strip():
            raise RuntimeError("Agent returned no answer")
        return {
            "answer": answer,
            "routing_preprocessor_decision": routing,
            "user_instructions_data_wrangling": result.get("user_instructions_data_wrangling"),
            "user_instructions_data_visualization": result.get("user_instructions_data_visualization"),
            "data_wrangler_function": result.get("data_wrangler_function"),
            "data_visualization_function": result.get("data_visualization_function"),
            "plotly_graph": json.dumps(result.get("plotly_graph"), default=str) if result.get("plotly_graph") else None,
            "plotly_error": result.get("plotly_error"),
        }

    def close(self):
        self._analyst = None


def create_graph():
    return AgentGraph()

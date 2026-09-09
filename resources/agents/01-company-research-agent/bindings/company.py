"""Company's explicit native lifecycle binding; upstream agent/ is unchanged."""
import asyncio
from uuid import uuid4


class CompanyGraph:
    def __init__(self):
        self.graph = None
        self.job_id = None

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from langchain_core.runnables import RunnableLambda
        return await RunnableLambda(self._run, name="company.research").ainvoke(value, config=config)

    async def _run(self, value, config):
        from backend.graph import Graph
        from backend.classes.state import job_status
        from langchain_core.callbacks.manager import adispatch_custom_event
        from agentbench.observe.google_rest import use_google_rest
        from agentbench.observe.tools import observe_async_methods

        if not isinstance(value, dict) or not isinstance(value.get("company"), str) or not value["company"].strip():
            raise ValueError("Company input requires a non-empty company string")
        allowed = {"company", "company_url", "url", "hq_location", "industry", "job_id"}
        if set(value) - allowed:
            raise ValueError(f"Unsupported Company input fields: {sorted(set(value) - allowed)}")
        if "url" in value and "company_url" in value and value["url"] != value["company_url"]:
            raise ValueError("url and company_url conflict")
        config = config or {}
        job_id = value.get("job_id") or config.get("metadata", {}).get("abb_run_id") or uuid4().hex
        self.job_id = job_id
        job_status[job_id].update(status="processing", company=value["company"], events=[])
        self.graph = Graph(company=value["company"], url=value.get("company_url", value.get("url")),
                           hq_location=value.get("hq_location"), industry=value.get("industry"), job_id=job_id)
        use_google_rest(self.graph.briefing.llm)
        for node in vars(self.graph).values():
            client = getattr(node, "tavily_client", None)
            if client is not None:
                observe_async_methods(client, ("search", "extract", "crawl"), namespace="tavily")
        report = None
        async for update in self.graph.run(config):
            for event in job_status[job_id]["events"]:
                await adispatch_custom_event("company.progress", event, config=config)
            job_status[job_id]["events"].clear()
            if isinstance(update, dict) and isinstance(update.get("editor"), dict):
                report = update["editor"].get("report")
        if not isinstance(report, str) or not report.strip():
            raise RuntimeError("Company editor completed without a non-empty report")
        return {"report": report, "company": value["company"], "job_id": job_id}

    def close(self):
        if self.job_id is not None:
            from backend.classes.state import job_status
            job_status.pop(self.job_id, None)
            self.job_id = None
        if self.graph is not None:
            self.graph.briefing.llm.client.transport.close()
            self.graph = None


def create_graph():
    return CompanyGraph()

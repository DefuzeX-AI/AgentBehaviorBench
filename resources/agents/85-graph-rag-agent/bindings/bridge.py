"""Invoke the upstream default RAG agent without removing its native search tool."""
import asyncio
import uuid

class NativeBinding:
    def invoke(self, value, config=None):
        from graphrag_agent.agents.naive_rag_agent import NaiveRagAgent
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        agent = NaiveRagAgent()
        try:
            result = agent.ask_with_trace(text, thread_id=uuid.uuid4().hex)
            errors = [event for event in result.get("execution_log", []) if event.get("node") == "error"]
            if errors:
                raise RuntimeError(str(errors))
            return result
        finally:
            agent.close()

    async def ainvoke(self, value, config=None):
        return await asyncio.to_thread(self.invoke, value, config)

def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return NativeBinding()

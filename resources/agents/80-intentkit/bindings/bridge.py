"""Invoke the upstream IntentKit graph with its shipped Code Explainer preset."""
import asyncio
import uuid

class NativeBinding:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from intentkit.config.config import config as native_config
        from intentkit.config import db
        from intentkit.config.redis import init_redis
        from intentkit.core.public_agents import ensure_public_agent_prerequisites, sync_public_agents
        from intentkit.core.agent import get_agent
        from intentkit.core.executor import build_executor
        from intentkit.models.agent_data import AgentData
        from intentkit.abstracts.graph import AgentContext
        from intentkit.models.chat import AuthorType
        from langchain_core.messages import HumanMessage
        redis = await init_redis(host=native_config.redis_host)
        try:
            await db.init_db(**native_config.db)
            await ensure_public_agent_prerequisites()
            await sync_public_agents()
            agent = await get_agent("public-code-explainer")
            if agent is None:
                raise RuntimeError("The native Code Explainer public agent was not initialized")
            # Only the deployment model changes; native prompt, tools and middleware remain.
            agent = agent.model_copy(update={"model": "gpt-4o-mini"})
            graph = await build_executor(agent, await AgentData.get(agent.id))
            thread = uuid.uuid4().hex
            context = AgentContext(agent_id=agent.id, get_agent=lambda: agent,
                chat_id=thread, entrypoint=AuthorType.API, is_own_team=False)
            run_config = dict(config or {})
            run_config["configurable"] = {**run_config.get("configurable", {}), "thread_id": context.thread_id}
            text = value.get("message", "") if isinstance(value, dict) else str(value)
            return await graph.ainvoke({"messages": [HumanMessage(content=text)]},
                config=run_config, context=context)
        finally:
            await redis.aclose()
            if db.connection_pool is not None:
                await db.connection_pool.close()
            if db.engine is not None:
                await db.engine.dispose()

def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return NativeBinding()

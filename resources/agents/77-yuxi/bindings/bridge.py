"""Run the native default chatbot with real native database identity/configuration."""
import asyncio
import secrets
import uuid

class Yuxi:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        from yuxi.bootstrap.app import main as initialize
        from yuxi.infrastructure.postgres.manager import pg_manager
        from yuxi.infrastructure.redis import close_async_redis_client
        from yuxi.modules.identity.services.administration import initialize_system_admin
        from yuxi.modules.models.providers.service import create_provider_config, get_all_model_providers
        from yuxi.modules.models.providers.cache import model_cache
        from yuxi.modules.agents.presets.default_chatbot import PRESET
        from yuxi.modules.agents.runtime.agent_backends.chatbot.context import ChatBotContext
        from yuxi.modules.agents.runtime.agent_backends.chatbot.graph import ChatbotAgent
        from yuxi.modules.agents.runtime.context import prepare_agent_runtime_context
        from yuxi.modules.agents.repositories.sessions import SessionRepository
        from yuxi.modules.workspace.services.projects import create_implicit_project
        from yuxi.modules.workspace.paths import ensure_bound_user_workdir
        from yuxi.modules.workspace.runtime_paths import runtime_workdir_path
        text = value.get("message") if isinstance(value, dict) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Expected a nonempty text message")
        await initialize()
        uid = "abb-smoke"
        try:
            async with pg_manager.get_async_session_context() as db:
                await initialize_system_admin(db, uid=uid, password=secrets.token_urlsafe(32), phone_number=None)
                await create_provider_config(db, {
                    "provider_id": "abb", "display_name": "ABB intercepted model",
                    "provider_type": "openai", "base_url": "https://api.openai.com/v1",
                    "api_key_env": "OPENAI_API_KEY", "is_enabled": True,
                    "capabilities": ["chat"], "enabled_models": [{"id": "gpt-4o-mini", "type": "chat", "source": "manual"}],
                }, username=uid)
                project = await create_implicit_project(uid=uid, db=db)
                session = await SessionRepository(db).add_session(uid=uid, agent_id=PRESET.slug,
                    project_id=project.id, title="ABB greeting")
                thread_id, workdir = session.thread_id, project.workdir_path
                providers = await get_all_model_providers(db)
                model_cache.rebuild(providers)
            ensure_bound_user_workdir(uid, workdir)
            context = ChatBotContext(uid=uid, thread_id=thread_id, agent_slug=PRESET.slug,
                model="abb:gpt-4o-mini", workdir_relative_path=workdir,
                workdir_path=runtime_workdir_path(workdir), **PRESET.context)
            await prepare_agent_runtime_context(context)
            graph = await ChatbotAgent().get_graph(context=context)
            cfg = dict(config or {})
            cfg["configurable"] = {**cfg.get("configurable", {}), "thread_id": thread_id, "uid": uid}
            return await graph.ainvoke({"messages": [{"role": "user", "content": text}]}, config=cfg, context=context)
        finally:
            await close_async_redis_client()
            await pg_manager.close()

def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return Yuxi()

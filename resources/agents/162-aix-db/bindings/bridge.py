"""Transport the native EnhancedCommonAgent's SSE response without changing its loop."""
import asyncio
import json
import os
import secrets
import uuid


class ResponseCollector:
    def __init__(self):
        self.events = []

    async def write(self, chunk):
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        for block in chunk.split("\n\n"):
            if block.startswith("data:"):
                self.events.append(json.loads(block[5:]))

    async def flush(self):
        pass


class NativeBinding:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from model.db_connection_pool import get_db_pool
        from model.db_models import TAiModel
        from services.user_service import add_user, authenticate_user, generate_jwt_token
        from agent.common.enhanced_common_agent import EnhancedCommonAgent
        pool = get_db_pool()
        pool.create_tables()
        password = secrets.token_urlsafe(24)
        username = "abb-" + uuid.uuid4().hex[:12]
        await add_user(username, password, mobile=None)
        user = await authenticate_user(username, password)
        if not user:
            raise RuntimeError("Native local user authentication failed")
        token = await generate_jwt_token(user["id"], username, role="user")
        with pool.get_session() as db:
            db.add(TAiModel(supplier=1, name="ABB model", model_type=1,
                base_model="gpt-4o-mini", default_model=True,
                api_key=os.environ["OPENAI_API_KEY"], api_domain="https://api.openai.com/v1"))
        response = ResponseCollector()
        try:
            text = value.get("message", "") if isinstance(value, dict) else str(value)
            await EnhancedCommonAgent().run_agent(text, response, session_id=uuid.uuid4().hex,
                uuid_str=uuid.uuid4().hex, user_token=token)
            errors = [e for e in response.events if isinstance(e.get("data"), dict)
                and e["data"].get("messageType") == "error"]
            if errors:
                raise RuntimeError(json.dumps(errors, ensure_ascii=False))
            if not response.events:
                raise RuntimeError("The native SSE stream produced no events")
            return {"events": response.events}
        finally:
            pool.engine.dispose()


def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return NativeBinding()

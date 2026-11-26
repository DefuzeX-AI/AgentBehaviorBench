"""Bind the native text action router, including persistence and memory processing."""
import asyncio
import os
from pathlib import Path
import runpy
import sys
from uuid import uuid4


class NativeBinding:
    async def ainvoke(self, value, config=None, **kwargs):
        from src import backend, routes
        text = value['message'] if isinstance(value, dict) else value
        existing_tasks = asyncio.all_tasks()
        try:
            # Use the native backend initializer before the text router queries it.
            await backend.init_tables()
            reply = await routes.action_router(text, thread_id=uuid4().hex)
            if 'relation "integrations" does not exist' in reply:
                raise RuntimeError(reply)
            # The native router schedules memory processing after returning its reply.
            pending = [task for task in asyncio.all_tasks() - existing_tasks
                       if getattr(task.get_coro(), '__name__', '') == '_background_memory_processing']
            if pending:
                await asyncio.gather(*pending)
            return {'messages': [{'role': 'assistant', 'content': reply}]}
        finally:
            await routes._close_persistence()
            if backend._db_pool is not None:
                await backend._db_pool.close()
                backend._db_pool = None

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    sys.path.insert(0, '/opt/agent/agent')
    os.environ['LITELLM_API_KEY'] = os.environ['OPENAI_API_KEY']
    os.environ['MODEL'] = 'gpt-4o-mini'
    os.environ['GPT_HOME_LOG_FILE'] = str(Path.home()/'gpt-home/events.log')
    runpy.run_path('/opt/agent/bootstrap/start.py', run_name='abb_deployment')
    return NativeBinding()

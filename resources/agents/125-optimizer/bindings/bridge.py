"""Preserve the native Fund cockpit Ask agent and turn runner."""
import asyncio
import runpy
from pathlib import Path

def create_graph():
    runpy.run_path("/opt/agent/bootstrap/start.py")
    from fund.config import settings
    from fund.database import get_session
    from fund.audit.persistence import setup_langgraph
    from fund.agents.model import build_primary
    from fund.agents.ask_agent import build_ask_agent,run_ask_turn,_STOPPED,_NO_ANSWER
    class NativeAsk:
        def invoke(self,inputs,config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():raise ValueError("Nonempty text required")
            persistence=setup_langgraph(settings)
            try:
                agent=build_ask_agent(model=build_primary(settings),session_factory=get_session,
                    persistence=persistence,scope="fund",focus=None,config=settings,
                    repo_root=Path("/opt/agent/agent"),runtime_root=Path.home()/"optimizer-runtime")
                answer=run_ask_turn(agent,scope="fund",question=text,max_steps=settings.ask_max_steps,
                    timeout_seconds=settings.ask_timeout_seconds)
                if not answer or answer in {_STOPPED,_NO_ANSWER}:
                    raise RuntimeError(answer or "Native Ask produced no answer")
                return answer
            finally:persistence.pool.close()
        async def ainvoke(self,inputs,config=None):return await asyncio.to_thread(self.invoke,inputs,config)
    return NativeAsk()

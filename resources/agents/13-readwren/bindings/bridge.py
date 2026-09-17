"""ABB message/result boundary for muratcankoylan/readwren.

Upstream entrypoint: src.agents.InterviewAgent, driven as cli_interview.py does: start_interview(thread_id) opens the session and returns the fixed first question, then send_message(user_message, thread_id) runs one interview turn. Redis is optional; the binding constructs the agent with use_redis=False so it uses the in-memory checkpointer. The Case Input is the user's reply to that opening question; the answer is the agent's next message.
"""
import asyncio
import uuid
from collections.abc import Mapping


class AgentGraph:
    def __init__(self):
        from src.agents import InterviewAgent

        self._agent = InterviewAgent(use_redis=False)
        self._thread = str(uuid.uuid4())
        self._agent.start_interview(thread_id=self._thread)

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        response = await asyncio.to_thread(self._agent.send_message, text, self._thread)
        answer = response.get("message") if isinstance(response, Mapping) else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._agent = None


def create_graph():
    return AgentGraph()

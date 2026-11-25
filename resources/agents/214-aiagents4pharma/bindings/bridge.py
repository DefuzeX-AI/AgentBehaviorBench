"""Expose the complete upstream pharmaceutical supervisor and its native tools."""
import uuid


class NativeBinding:
    def invoke(self, value, config=None):
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI
        from aiagents4pharma.talk2aiagents4pharma.agents.main_agent import get_app

        text = value.get("message", "") if isinstance(value, dict) else str(value)
        thread = uuid.uuid4().hex
        model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        app = get_app(thread, model)
        run_config = dict(config or {})
        run_config["configurable"] = {**run_config.get("configurable", {}), "thread_id": thread}
        return app.invoke({"messages": [HumanMessage(content=text)], "llm_model": model,
                           "uploaded_files": [], "selections": {}}, config=run_config)


def create_graph():
    return NativeBinding()

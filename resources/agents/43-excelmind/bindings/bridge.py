"""Binding for ExcelMind's real non-streaming /chat LangGraph path.

Preload an operator-supplied workbook through the native loader, as /load does.
No chat input is interpreted as a filename, spreadsheet or configuration.
"""
import os
from pathlib import Path


class ExcelMindBinding:
    def __init__(self, workbook, *, sheet_name=None):
        from excel_agent.excel_loader import get_loader, reset_loader
        from excel_agent.graph import get_graph, reset_graph
        reset_loader()
        get_loader().add_table(str(Path(workbook).resolve()), sheet_name)
        reset_graph()
        self.graph = get_graph()

    def invoke(self, value, config=None):
        from langchain_core.messages import HumanMessage, AIMessage
        if not isinstance(value, str):
            raise TypeError('ExcelMind chat accepts a text message')
        # Matches native api.chat input and response extraction. No invented
        # conversation memory: upstream /chat does not use request.history.
        result = self.graph.invoke({'messages': [HumanMessage(content=value)],
                                    'is_relevant': True}, config=config)
        answer = ''
        tool_calls = []
        for message in result.get('messages', []):
            if isinstance(message, AIMessage):
                if message.content:
                    answer = message.content
                if message.tool_calls:
                    tool_calls.extend({'name': item['name'], 'args': item['args']}
                                      for item in message.tool_calls)
        return {'response': answer, 'tool_calls': tool_calls or None}

    def close(self):
        from excel_agent.excel_loader import reset_loader
        from excel_agent.graph import reset_graph
        reset_graph()
        reset_loader()


def create_graph():
    from excel_agent.config import AppConfig, ModelConfig, ProviderConfig, set_config
    key = os.environ.get('OPENAI_API_KEY')
    workbook = os.environ.get('EXCELMIND_WORKBOOK')
    if not key or not workbook:
        raise ValueError('OPENAI_API_KEY and EXCELMIND_WORKBOOK are required')
    # Native public configuration API; model credentials come from ABB's
    # injected interception credential, never a committed config.yaml.
    config = AppConfig(model=ModelConfig(active='abb', providers={'abb': ProviderConfig(
        model_name=os.environ.get('OPENAI_MODEL', 'gpt-4'), api_key=key,
        base_url='https://api.openai.com/v1')}))
    set_config(config)
    return ExcelMindBinding(workbook, sheet_name=os.environ.get('EXCELMIND_SHEET'))

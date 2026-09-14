"""Translate a Case conversation into the official TradingAgents graph state."""
import json
from copy import deepcopy
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path


def request_from_messages(messages, *, defaults=None):
    """Return configured ticker/date, explicit user overrides and unchanged history.

    Args:
        messages: Current Case's ordered user/assistant dictionaries. User JSON
            can supply {ticker, date, request}; plain text uses configured values.
            No field is inferred from an assistant's answer.
        defaults: Optional deployment ticker/date declared in adapter.context and
            the Agent Profile. Without defaults, user JSON must supply both.
    Returns:
        A (ticker, ISO date, serialized conversation) tuple for native graph state.
    Raises:
        ValueError: Missing/invalid identity, date or conversation format.
    """
    if not isinstance(messages, list) or not messages:
        raise ValueError('Supply a non-empty messages list')
    request = {key: value for key, value in (defaults or {}).items() if key in ('ticker', 'date')}
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('user', 'assistant'):
            raise ValueError('Expected user/assistant conversation messages')
        content = message.get('content')
        if not isinstance(content, str):
            raise ValueError('Conversation content must be text')
        if message['role'] != 'user':
            continue
        try:
            fields = json.loads(content)
        except json.JSONDecodeError:
            continue  # Plain text keeps the configured or explicitly updated identity.
        if isinstance(fields, dict):
            request.update({key: fields[key] for key in ('ticker', 'date') if key in fields})
    ticker = request.get('ticker')
    if not isinstance(ticker, str) or not ticker.strip() or len(ticker) > 32:
        raise ValueError('Specify a ticker through deployment defaults or user JSON')
    if any(char in ticker for char in ('/', '\\', '\x00')) or '..' in ticker:
        raise ValueError('Ticker must be a symbol, not a path')
    try:
        trade_date = date.fromisoformat(request.get('date', '')).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError('Specify an explicit date as YYYY-MM-DD') from exc
    return ticker.strip(), trade_date, json.dumps(messages, ensure_ascii=False)


class TradingGraph:
    def invoke(self, value, config=None, *, context=None):
        """Run the upstream market/debate/risk workflow and return its final answer.

        Args:
            value: Native {messages: [...]} or an observe {ticker, date, request}.
            config: Process-local LangChain RunnableConfig, including callbacks.
            context: Deployment settings for model, debate rounds and token cap.
        Returns:
            {answer: original final_trade_decision}; no order is executed.
        """
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        if not isinstance(value, dict):
            raise ValueError('Expected a native request object')
        messages = value.get('messages')
        if messages is None:
            messages = [{'role': 'user', 'content': json.dumps(value)}]
        settings = dict(context or {})
        ticker, trade_date, history = request_from_messages(messages,
                                        defaults=settings.get('research_defaults'))
        with TemporaryDirectory(prefix='abb-trading-') as directory:
            root = Path(directory)
            options = deepcopy(DEFAULT_CONFIG)
            # The gateway speaks Chat Completions. Native 'openai' opts into
            # Responses; use the upstream compatible-provider configuration.
            options.update(llm_provider=settings.get('provider', 'openai_compatible'),
                           backend_url='https://api.openai.com/v1',
                           deep_think_llm=settings.get('model', 'gpt-4.1-mini'),
                           quick_think_llm=settings.get('model', 'gpt-4.1-mini'),
                           results_dir=str(root/'reports'), data_cache_dir=str(root/'cache'),
                           memory_log_path=str(root/'memory.md'), checkpoint_enabled=False,
                           max_debate_rounds=settings.get('debate_rounds', 1),
                           max_risk_discuss_rounds=settings.get('risk_rounds', 1),
                           max_tokens=settings.get('max_tokens', 2500))
            # Native keyless data vendor; the market analyst needs no FRED key.
            options['data_vendors'] = dict(options['data_vendors'],
                                          core_stock_apis='yfinance', technical_indicators='yfinance')
            graph = TradingAgentsGraph(selected_analysts=['market'], config=options)
            identity = graph.resolve_instrument_context(ticker, 'stock')
            state = graph.propagator.create_initial_state(ticker, trade_date,
                         past_context=history, instrument_context=identity)
            state['messages'] = messages
            run_config = dict(config or {})
            run_config.setdefault('recursion_limit', 100)
            # Native propagate() does not forward tool callbacks. Drive the same
            # compiled graph with the process-local config so children are observed.
            final = graph.graph.invoke(state, config=run_config)
            answer = final.get('final_trade_decision')
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError('TradingAgents returned no final trade decision')
            return {'answer': answer, 'research_request': {'ticker': ticker, 'date': trade_date}}

    def close(self):
        pass


def create_graph():
    return TradingGraph()

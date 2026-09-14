"""Map the current research request to the official TradingAgents graph state."""
import json
from copy import deepcopy
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path


def request_from_input(value, *, defaults=None):
    """Resolve deployment parameters using only the current Input.

    Args:
        value: Current text or {ticker, date, request} request. JSON text may
            provide the same fields. Plain text uses the deployment defaults.
        defaults: Optional deployment ticker/date declared in adapter.context and
            the Agent Profile. Without defaults, user JSON must supply both.
    Returns:
        A (ticker, ISO date, current request text) tuple for native graph state.
    Raises:
        ValueError: Missing/invalid ticker, date, request or a history envelope.
    """
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = None
        value = decoded if isinstance(decoded, dict) else {'request': value}
    if not isinstance(value, dict) or 'messages' in value:
        raise ValueError('Supply the current research request, not a messages history')
    # The generic adapter wraps text in {request: text}. Decode explicit JSON
    # from that field too; this is field mapping, never conversation recovery.
    if set(value) == {'request'} and isinstance(value['request'], str):
        try:
            decoded = json.loads(value['request'])
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            value = decoded
    if 'messages' in value:
        raise ValueError('Supply the current research request, not a messages history')
    request = {key: value for key, value in (defaults or {}).items() if key in ('ticker', 'date')}
    request.update({key: value[key] for key in ('ticker', 'date') if key in value})
    ticker = request.get('ticker')
    if not isinstance(ticker, str) or not ticker.strip() or len(ticker) > 32:
        raise ValueError('Specify a ticker through deployment defaults or user JSON')
    if any(char in ticker for char in ('/', '\\', '\x00')) or '..' in ticker:
        raise ValueError('Ticker must be a symbol, not a path')
    try:
        trade_date = date.fromisoformat(request.get('date', '')).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError('Specify an explicit date as YYYY-MM-DD') from exc
    question = value.get('request', '')
    if not isinstance(question, str):
        raise ValueError('request must be text')
    return ticker.strip(), trade_date, question


class TradingGraph:
    def __init__(self):
        self._directory = None
        self._native = None

    def _load_native(self, settings):
        """Create the native agent once; its writable files live until close()."""
        if self._native is not None:
            return self._native
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        self._directory = TemporaryDirectory(prefix='abb-trading-')
        root = Path(self._directory.name)
        options = deepcopy(DEFAULT_CONFIG)
        # The gateway speaks Chat Completions. Native 'openai' opts into
        # Responses; use the upstream compatible-provider configuration.
        options.update(llm_provider=settings.get('provider', 'openai_compatible'),
                       backend_url='https://api.openai.com/v1',
                       deep_think_llm=settings.get('model', 'gpt-4.1-mini'),
                       quick_think_llm=settings.get('model', 'gpt-4.1-mini'),
                       results_dir=str(root/'reports'), data_cache_dir=str(root/'cache'),
                       memory_log_path=str(root/'memory.md'),
                       max_debate_rounds=settings.get('debate_rounds', 1),
                       max_risk_discuss_rounds=settings.get('risk_rounds', 1),
                       max_tokens=settings.get('max_tokens', 2500))
        # Native keyless data vendor; the market analyst needs no FRED key.
        options['data_vendors'] = dict(options['data_vendors'],
                                      core_stock_apis='yfinance', technical_indicators='yfinance')
        try:
            self._native = TradingAgentsGraph(selected_analysts=['market'], config=options)
        except BaseException:
            self.close()
            raise
        return self._native

    def invoke(self, value, config=None, *, context=None):
        """Run the upstream market/debate/risk workflow and return its final answer.

        Args:
            value: Current text or native {ticker, date, request} object.
            config: Process-local LangChain RunnableConfig, including callbacks.
            context: Deployment settings for model, debate rounds and token cap.
        Returns:
            {answer: original final_trade_decision}; no order is executed.
        """
        settings = dict(context or {})
        ticker, trade_date, question = request_from_input(value,
                                        defaults=settings.get('research_defaults'))
        graph = self._load_native(settings)
        identity = graph.resolve_instrument_context(ticker, 'stock')
        state = graph.propagator.create_initial_state(ticker, trade_date,
                     past_context=question, instrument_context=identity)
        state['messages'] = [{'role': 'user', 'content': question or ticker}]
        run_config = dict(config or {})
        run_config.setdefault('recursion_limit', 100)
        # Drive the compiled native workflow with process-local callbacks. This
        # task entrypoint does not implement native propagate()'s investment-log
        # lifecycle or claim that old decisions become conversational memory.
        final = graph.graph.invoke(state, config=run_config)
        answer = final.get('final_trade_decision')
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError('TradingAgents returned no final trade decision')
        return {'answer': answer, 'research_request': {'ticker': ticker, 'date': trade_date}}

    def close(self):
        """Release this binding and its private native cache/report files."""
        self._native = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None


def create_graph():
    return TradingGraph()

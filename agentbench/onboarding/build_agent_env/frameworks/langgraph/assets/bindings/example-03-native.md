# Example 03: call the full native public task API

This is the complete existing TradingAgents binding. Its saved manifest declares
`binding="trading.py:create_graph"`, graph ID `agent` in the existing
`abb-langgraph.json`, and no output_key. The image installs `tradingagents`,
LangChain, and the Agent's dependencies.

Input example: `{"ticker": "AAPL", "date": "2026-09-14"}`. The same JSON encoded
as text is supported. The wrapper validates both fields and calls the public
`propagate()` method, which owns native execution and postprocessing. It returns
both native values as `{final_state: ..., decision: ...}` without inventing a
trade or relabeling an intermediate report. This is a synchronous API, so no
ainvoke implementation is needed: BBA's async adapter supplies the thread fallback.

`config` travels through the installed framework's `set_config_context` because
this public method does not take a config argument. `context` separately supplies
this deployment's model/budget settings. Temporary reports and cache are owned by
the binding and removed on close; they are not persistent benchmark artifacts.

IMPORTANT: this historical deployment deliberately selects a market analyst,
yfinance, provider settings, and debate limits. Those are NOT general BBA defaults.
Do not apply these choices to another Agent without explicit deployment evidence.
Do not add memory configuration merely because this example has a native setting.
The existing source config is a prerequisite, not something to fabricate.

Source snapshot: `resources/agents/03-trading-agents/bindings/trading.py`.

```python
"""Call TradingAgents' public task API; native code owns decisions and memory."""
import json
from copy import deepcopy
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path


def request_from_input(value):
    """Validate the explicit arguments supported by the native stock task API.

    Args:
        value: A {ticker, date} object or its JSON text representation. Both
            fields are required on every Input; no prior values are inferred.
    Returns:
        A (ticker, ISO date) tuple for native propagate(company_name, trade_date).
    Raises:
        ValueError: Freeform questions, missing/extra fields, or invalid values.
            Rejected input is not silently dropped or presented as past memory.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError('TradingAgents requires a JSON object with ticker and date; freeform chat is unsupported') from exc
    if not isinstance(value, dict) or set(value) != {'ticker', 'date'}:
        raise ValueError('TradingAgents requires exactly ticker and date; request/messages and other extra fields are unsupported')
    ticker = value['ticker']
    if not isinstance(ticker, str) or not ticker or ticker.strip() != ticker or len(ticker) > 32:
        raise ValueError('ticker must be a non-empty symbol without surrounding whitespace')
    if any(char in ticker for char in ('/', '\\', '\x00')) or '..' in ticker:
        raise ValueError('Ticker must be a symbol, not a path')
    try:
        trade_date = date.fromisoformat(value['date']).isoformat()
        if trade_date != value['date']:
            raise ValueError('Non-canonical date')
    except (TypeError, ValueError) as exc:
        raise ValueError('Specify an explicit date as YYYY-MM-DD') from exc
    return ticker, trade_date


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
        """Run the public native lifecycle and preserve both public return values.

        Args:
            value: Explicit {ticker, date} object or JSON-encoded text.
            config: Process-local LangChain RunnableConfig, including callbacks
                inherited by native graph, tool and reflection invocations.
            context: Deployment settings for model, debate rounds and token cap.
        Returns:
            {final_state: native complete state, decision: native rating signal}.
            Intermediate reports retain their original names in final_state;
            they are never relabeled as the final decision. No order is executed.
        """
        settings = dict(context or {})
        ticker, trade_date = request_from_input(value)
        graph = self._load_native(settings)
        from langchain_core.runnables.config import set_config_context

        run_config = dict(config or {})
        # propagate() owns pending-outcome reflection, native memory retrieval,
        # graph execution, logging and checkpoint cleanup. LangChain's child
        # config context observes that entire call without replacing its methods.
        with set_config_context(run_config) as invocation_context:
            final_state, decision = invocation_context.run(
                graph.propagate, ticker, trade_date, asset_type='stock')
        return {'final_state': final_state, 'decision': decision}

    def close(self):
        """Release this binding and its private native cache/report files."""
        self._native = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None


def create_graph():
    return TradingGraph()
```

"""Bridge one BBA text Case into TimeSeriesScientist's public workflow.

Native entrypoint (source-confirmed)
------------------------------------
time_series_agent/graph/agent_graph.py defines
``TimeSeriesAgentGraph(config, model, debug)``. Its constructor instantiates a
``FileManager`` plus the five agents (Preprocess/Analysis/Validation/Forecast/
Report) and compiles the LangGraph workflow onto ``self.graph``. The public
business workflow is ``TimeSeriesAgentGraph.run()``; the upstream CLI caller
(time_series_agent/main.py) copies ``DEFAULT_CONFIG``, sets ``num_slices``,
``input_length``, ``horizon``, ``data_path`` and ``llm_model``, builds the graph
object and calls ``run()``. ``run()`` itself loads the CSV
(``DataLoader.load_data(config['data_path'])``), converts it to a time series
(``date_column``/``value_column``), slices it
(``DataSplitter.create_slices`` with ``num_slices``/``input_length``/``horizon``),
invokes the compiled graph once per slice, and averages per-slice results in
``_aggregate_slice_results``. It returns
``{'all_results', 'aggregated_results', 'report'}``.

Why this binding does more than forward a graph
-----------------------------------------------
The compiled ``self.graph`` expects a mapping state that already contains pandas
``validation_data``/``test_data`` frames and a ``slice_info`` block, which SDK
text cannot supply. The upstream CLI caller performs the parsing, config
construction and state setup; the ABB worker does NOT run that CLI, so this
binding reproduces the caller's setup and invokes the public ``run()``.

Input and output
----------------
Input: the SDK supplies TEXT. With ``input_key="request"`` the adapter wraps a
scalar Case into ``{'request': <text>}``; this binding also accepts raw text or an
already-mapping request document. The native workflow consumes a CSV and run
configuration, not free-form prompt text. Optional numeric run overrides may be
given as a JSON object or as ``LABEL: value`` lines. Other non-empty text triggers
the default workflow and is not passed to the native agents. The dataset is chosen
by the deployment or the packaged ETTh1 sample; a Case cannot supply a file path.
Business defaults start at ``DEFAULT_CONFIG``; optional deployment defaults
and explicit supported Case values override them. Native orchestration argument
omissions are repaired in a deployment subclass, without editing upstream source.
Output: the native ``run()`` dict, unchanged — ``all_results``,
``aggregated_results`` and ``report``. No answer is fabricated.

Config / context / resources
----------------------------
``config`` (callbacks, tags, metadata, thread_id) is preserved and forwarded to
the native graph via ``set_config_context`` and a per-slice runnable context.
Credentials are read from the environment by NAME only (``OPENAI_API_KEY``) and
never printed. Output is written to a writable container path; when none is
given, a private ``TemporaryDirectory`` is used and released in ``close()``,
which is safe to repeat and after partial initialization.

Example input
-------------
``{"num_slices": 1, "horizon": 96, "k_models": 1}``
(the packaged ETTh1 dataset is used unless the operator sets ``TSCI_DATA_PATH``).
"""

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Labels understood for the simple ``LABEL: value`` text form. JSON object
# requests use the same keys. Only these keys may be overridden from the request;
# every other native default is preserved.
_OPTION_KEYS = {
    "num_slices",
    "input_length",
    "horizon",
    "k_models",
}

# These four numeric options are the only Case-controlled settings. Filesystem,
# model endpoint, debug and output-directory settings remain deployment-owned.
_KNOWN_TEXT = {
    "num_slices": int,
    "input_length": int,
    "horizon": int,
    "k_models": int,
}

_LIMITS = {
    "num_slices": (1, 25),
    "input_length": (100, 100000),
    "horizon": (1, 10000),
    "k_models": (1, 21),
}


def _coerce(key, raw):
    """Validate one explicit override value against its native type."""
    expected = _KNOWN_TEXT[key]
    if expected is bool:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        raise ValueError(f"{key} must be a boolean")
    if expected is int:
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be an integer, not a boolean")
        text = str(raw).strip()
        if not text.isdigit():
            raise ValueError(f"{key} must be an integer")
        value = int(text)
        minimum, maximum = _LIMITS[key]
        if not minimum <= value <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return value
    raise ValueError(f"Unsupported option: {key}")


def request_from_input(value):
    """Split one Case input into free text and explicitly supplied overrides.

    Args:
        value: The adapter value for this Case: ``{'request': <text>}`` from
            ``input_key = "request"``, a raw mapping request document, or plain
            text. A JSON object (in text or mapping form) may carry the native
            option keys ``num_slices``, ``input_length``, ``horizon`` and
            ``k_models``. A ``LABEL: value`` line form is also accepted. Plain
            natural-language text triggers the default workflow but is not used
            as an instruction to the native graph.
    Returns:
        A ``(text, overrides)`` tuple. ``text`` is the preserved request text;
        ``overrides`` contains only bounded numeric run options.
    Raises:
        ValueError: Empty input, malformed structured input, duplicate or
            unknown fields, or an invalid value for a recognised option.
    """
    def parse_text(text):
        """Parse one text request while preserving ordinary prose."""
        overrides = {}
        if not isinstance(text, str):
            raise ValueError("request must be a string")
        stripped = text.strip()
        if not stripped:
            raise ValueError("Supply a non-empty request")

        if stripped.startswith("{"):
            def reject_duplicate_fields(pairs):
                parsed = {}
                for key, raw in pairs:
                    if key in parsed:
                        raise ValueError(f"Duplicate request field: {key}")
                    parsed[key] = raw
                return parsed

            try:
                parsed = json.loads(stripped, object_pairs_hook=reject_duplicate_fields)
            except json.JSONDecodeError as exc:
                raise ValueError("Malformed JSON request object") from exc
            if not isinstance(parsed, dict):
                raise ValueError("JSON request must be an object")
            unrecognised = set(parsed) - _OPTION_KEYS
            if unrecognised:
                raise ValueError(
                    "Unsupported request field(s): "
                    + ", ".join(sorted(unrecognised))
                )
            for key, raw in parsed.items():
                overrides[key] = _coerce(key, raw)
            return overrides

        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        option_lines = [
            line for line in lines
            if ":" in line
            and line.split(":", 1)[0].strip().lower() in _OPTION_KEYS
        ]
        if option_lines:
            if len(option_lines) != len(lines):
                raise ValueError(
                    "Parameter input must contain only supported key: value lines"
                )
            for line in lines:
                key, raw = line.split(":", 1)
                key = key.strip().lower()
                if key in overrides:
                    raise ValueError(f"Duplicate request field: {key}")
                overrides[key] = _coerce(key, raw.strip())
            return overrides

        # Plain natural-language request: preserve it, but do not use it as an
        # instruction to the native pipeline.
        return overrides

    if isinstance(value, dict):
        data = dict(value)
        text = data.pop("request", None)
        unrecognised = set(data) - _OPTION_KEYS
        if unrecognised:
            raise ValueError(
                "Unsupported request field(s): "
                + ", ".join(sorted(unrecognised))
            )
        overrides = {key: _coerce(key, raw) for key, raw in data.items()}
        if text is None:
            if not overrides:
                raise ValueError("Supply a non-empty request")
            return "", overrides
        if not isinstance(text, str):
            raise ValueError("request must be a string")
        parsed_overrides = parse_text(text)
        duplicate = set(overrides) & set(parsed_overrides)
        if duplicate:
            raise ValueError(
                "Duplicate request field(s): " + ", ".join(sorted(duplicate))
            )
        overrides.update(parsed_overrides)
        return text, overrides

    if not isinstance(value, str):
        raise ValueError("TimeSeriesScientist expects text or a request mapping")
    text = value
    stripped = text.strip()
    if not stripped:
        raise ValueError("Supply a non-empty request")
    return text, parse_text(text)


def _resolve_data_path():
    """Return the CSV location required by the native config.

    Native ``DEFAULT_CONFIG['data_path']`` is ``None``. Data selection belongs
    to the deployment: use an operator-set TSCI_DATA_PATH, then the packaged
    ETTh1 sample. Case inputs cannot select arbitrary container files.
    """
    env_path = os.environ.get("TSCI_DATA_PATH")
    if env_path:
        candidate = Path(env_path).resolve()
        if candidate.is_file():
            return str(candidate)
        raise ValueError("TSCI_DATA_PATH does not name a readable file")
    source_root = Path(__file__).resolve().parents[1]
    candidate = source_root / "agent" / "dataset" / "ETTh1.csv"
    if candidate.is_file():
        return str(candidate.resolve())
    raise ValueError(
        "No dataset available: set TSCI_DATA_PATH or include the packaged ETTh1.csv"
    )


def _deployment_int(name, default, minimum, maximum):
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        result = int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


class _ModelBudget:
    """One budget shared by all native models; never retries failed calls."""
    def __init__(self, maximum):
        self.maximum = maximum
        self.used = 0
        self.exhausted = False
        self.truncated = False

    def claim(self, messages):
        if self.truncated:
            raise RuntimeError("Deployment model output truncated; further calls rejected")
        size = sum(len(str(getattr(message, "content", message)))
                   for message in messages) if isinstance(messages, (list, tuple)) else len(str(messages))
        if self.used >= self.maximum or size > 60000:
            self.exhausted = True
            raise RuntimeError("Deployment model call/input budget exceeded")
        self.used += 1


class _BudgetedModel:
    """Delegate to the real instrumented client, with a shared call counter."""
    def __init__(self, client, budget, *, structured=False, return_raw=False):
        self.client = client
        self.budget = budget
        self.structured = structured
        self.return_raw = return_raw

    def __getattr__(self, name):
        return getattr(self.client, name)

    def invoke(self, messages, *args, **kwargs):
        self.budget.claim(messages)
        return self._check_response(self.client.invoke(messages, *args, **kwargs))

    async def ainvoke(self, messages, *args, **kwargs):
        self.budget.claim(messages)
        return self._check_response(await self.client.ainvoke(messages, *args, **kwargs))

    def _check_response(self, response):
        raw = response.get("raw") if self.structured and isinstance(response, dict) else response
        metadata = getattr(raw, "response_metadata", None) or {}
        if metadata.get("finish_reason") == "length":
            self.budget.truncated = True
            raise RuntimeError("Deployment model output truncated (finish_reason=length)")
        if self.structured and not self.return_raw:
            if not isinstance(response, dict) or "raw" not in response:
                raise RuntimeError("Structured model response is missing raw evidence")
            error = response.get("parsing_error")
            if error is not None:
                if isinstance(error, Exception):
                    raise error
                raise RuntimeError("Structured model response parsing failed")
            if response.get("parsed") is None:
                raise RuntimeError("Structured model response has no parsed result")
            return response["parsed"]
        return response

    def with_structured_output(self, *args, **kwargs):
        # Structured validation uses a derived Runnable, not client.invoke().
        # Keep that path on the same budget rather than delegating unguarded.
        options = dict(kwargs)
        return_raw = options.get("include_raw", False)
        options["include_raw"] = True
        return _BudgetedModel(self.client.with_structured_output(*args, **options),
                              self.budget, structured=True, return_raw=return_raw)


def _deployment_graph_class():
    from graph.agent_graph import TimeSeriesAgentGraph

    class DeploymentGraph(TimeSeriesAgentGraph):
        # Repair orchestration arguments only. All native algorithms and the
        # original source remain unchanged; results and errors are not replaced.
        def _preprocess_node(self, state):
            result = self.preprocess_agent.run(
                state["validation_data"], output_dir=self.config["output_dir"])
            state["preprocessed_data"] = (result if not isinstance(result, dict)
                                          else result.get("cleaned_data", state["validation_data"]))
            state["preprocess_result"] = result
            return state

        def _forecast_node(self, state):
            result = self.forecast_agent.run(
                selected_models=state["selected_models"],
                best_hyperparameters=state["best_hyperparameters"],
                validation_data=state["preprocessed_data"],
                test_data=state["test_data"],
                output_dir=self.config["output_dir"],
                validation_metrics=state.get("model_validation_scores", {}))
            state["forecast_result"] = result
            return state

    return DeploymentGraph


class TimeSeriesScientistWorkflow:
    """Own one TimeSeriesAgentGraph and run its public workflow per input."""

    def __init__(self):
        self._directory = None
        self._native = None
        self._native_config = None
        self._model_budget = None
        self._closed = False

    def _workspace(self):
        """Return a private writable output root for this invocation."""
        if self._directory is None:
            self._directory = TemporaryDirectory(prefix="abb-tsci-")
        return str(Path(self._directory.name) / "results")

    def _load_native(self, config):
        """Build the native graph once; import here so the factory stays light."""
        if self._native is not None and self._native_config == config:
            return self._native
        graph_class = _deployment_graph_class()

        self._native = graph_class(
            config=config,
            model=config["llm_model"],
            debug=config["debug"],
        )
        # Parameter changes may rebuild the native graph inside one Case.
        # Keep the same budget so reconfiguration cannot replenish paid calls.
        if self._model_budget is None:
            self._model_budget = _ModelBudget(_deployment_int("TSCI_MODEL_MAX_CALLS", 24, 1, 100))
        max_tokens = _deployment_int("TSCI_MODEL_OUTPUT_LIMIT", 1024, 128, 4096)
        effort = os.environ.get("TSCI_REASONING_EFFORT", "").strip()
        if effort and effort not in {"low", "high", "max"}:
            raise ValueError("TSCI_REASONING_EFFORT must be low, high or max")
        for name in ("preprocess_agent", "analysis_agent", "validation_agent",
                     "forecast_agent", "report_agent"):
            agent = getattr(self._native, name)
            client = agent.llm
            client.max_tokens = max_tokens
            client.max_retries = 0
            client.request_timeout = 60
            # ChatOpenAI constructs SDK clients during initialization: updating
            # Pydantic fields alone does not update their timeout/retry policy.
            if getattr(client, "root_client", None) is not None:
                client.root_client = client.root_client.with_options(timeout=60, max_retries=0)
                client.client = client.root_client.chat.completions
            if getattr(client, "root_async_client", None) is not None:
                client.root_async_client = client.root_async_client.with_options(timeout=60, max_retries=0)
                client.async_client = client.root_async_client.chat.completions
            if effort:
                client.extra_body = {**(client.extra_body or {}),
                                     "thinking": {"type": "enabled"},
                                     "reasoning_effort": effort}
            agent.llm = _BudgetedModel(client, self._model_budget)
            tools = getattr(agent, "tools", None)
            if tools is not None and hasattr(tools, "llm"):
                tools.llm = agent.llm
        self._native_config = dict(config)
        return self._native

    def _build_config(self, overrides):
        """Start from native defaults and apply only explicit overrides."""
        from config.default_config import DEFAULT_CONFIG

        config = {key: value for key, value in DEFAULT_CONFIG.items()}
        config["data_path"] = _resolve_data_path()
        config["output_dir"] = self._workspace()
        for key, bounds in _LIMITS.items():
            config[key] = _deployment_int("TSCI_DEPLOY_" + key.upper(), config[key], *bounds)
        for key, value in overrides.items():
            config[key] = value
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError(
                "OPENAI_API_KEY must be supplied by model interception"
            )
        return config

    def invoke(self, value, config=None, *, context=None):
        """Run the native workflow and return its aggregated result unchanged.

        Args:
            value: ``{'request': <text>}`` (adapter input_key), a request mapping,
                or plain text carrying optional ``LABEL: value`` overrides.
            config: Process-local LangChain RunnableConfig, forwarded to the
                native graph so callbacks/tags/metadata survive.
            context: Unused optional deployment context; native defaults are
                preserved unless a request field overrides them.
        Returns:
            The native ``run()`` dict: ``all_results``, ``aggregated_results``,
            ``report``. Intermediate per-slice reports keep their native names.
        Raises:
            ValueError: invalid / empty input or a missing required dataset.
            RuntimeError: the native workflow returned no aggregated result.
        """
        text, overrides = request_from_input(value)
        _ = text  # free text is preserved in the docstring example and NOT split
        if self._closed:
            raise RuntimeError("TimeSeriesScientist workflow is closed")

        native_config = self._build_config(overrides)
        self._load_native(native_config)

        run_config = dict(config or {})
        try:
            from langchain_core.runnables.config import set_config_context
        except Exception:  # pragma: no cover - framework always supplies this
            set_config_context = None

        native = self._native
        if set_config_context is not None:
            with set_config_context(run_config) as invocation_context:
                result = invocation_context.run(native.run)
        else:  # pragma: no cover
            result = native.run()

        if self._model_budget.exhausted:
            raise RuntimeError("Deployment model budget exhausted; incomplete result rejected")
        # Native nodes may catch model exceptions and continue with fallbacks.
        # A provider-reported truncation must still prevent a success-looking
        # Case result. Do not retry or increase paid limits automatically.
        if self._model_budget.truncated:
            raise RuntimeError("Deployment model output truncated; incomplete result rejected")
        if not isinstance(result, dict) or not result.get("aggregated_results"):
            raise RuntimeError(
                "Native workflow completed without aggregated results"
            )
        return result

    async def ainvoke(self, value, config=None, *, context=None):
        """Await the native workflow; the native API is synchronous."""
        return await asyncio.to_thread(self._invoke_sync, value, config, context)

    def _invoke_sync(self, value, config, context):
        return self.invoke(value, config=config, context=context)

    def close(self):
        """Release the native graph and this instance's private workspace."""
        self._closed = True
        self._native = None
        self._native_config = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

    async def aclose(self):
        """Async cleanup path; delegates to the synchronous release."""
        self.close()


def create_graph():
    """Return a fresh binding instance; callable without arguments.

    Example input: ``{'request': 'num_slices: 2\nhorizon: 96'}`` (or the same JSON
    encoded as text, or plain natural-language text). Output shape:
    ``{'all_results': [...], 'aggregated_results': {...}, 'report': {...}}``.
    """
    return TimeSeriesScientistWorkflow()

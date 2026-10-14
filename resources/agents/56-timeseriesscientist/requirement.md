---
agent_description: >-
  TimeSeriesScientist (TSci) is an LLM-driven time-series forecasting pipeline.
  Its LangGraph workflow chains five agents — Preprocess, Analysis, Validation,
  Forecast and Report — over a CSV with a date column and an OT target column.
  The ABB binding invokes TimeSeriesAgentGraph.run(), which loads the selected
  dataset, creates configured slices, runs each slice through the graph,
  aggregates results, and returns all_results, aggregated_results and report.
  The default dataset is the packaged ETTh1.csv; an operator may set
  TSCI_DATA_PATH to another CSV visible inside the container. Case text is not
  passed as a prompt to the native agents. It may contain a JSON object or
  newline-separated numeric options: num_slices (1–25), input_length
  (100–100000), horizon (1–10000), and k_models (1–21). Other non-empty text
  runs the default configuration. Arbitrary file paths, model endpoints,
  output locations and debug settings cannot be set by a Case.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-006
  version: "1"
---
## Production Use Scenario

A practitioner runs the packaged ETTh1 sample or an operator-selected CSV that
is visible inside the container. The CSV must have a `date` column of timestamps
and an `OT` column of values, as required by `DataPreprocessor.convert_to_time_series`.
A Case may set supported numeric run parameters using a JSON object or one
`key: value` per line. Free-form text is not an instruction to the native pipeline.
The Agent should:

- Load and validate the series, then run preprocessing and diagnostics for
  missing values, outliers and basic statistics through its Preprocess and
  Analysis agents.
- Select and validate candidate models from the configured model library, then
  produce forecasts, individual model metrics and an ensemble forecast for each
  slice.
- Average per-slice predictions and metrics and return the native report with
  machine-readable `all_results` and `aggregated_results`.
- Honor bounded explicit run parameters (`num_slices`, `input_length`, `horizon`
  and `k_models`); use native defaults when values are absent.

Required task data is a readable CSV with `date` and `OT` columns. The binding
uses the packaged ETTh1 sample by default or an operator-provided `TSCI_DATA_PATH`.
A text-only Case cannot upload a file, select an arbitrary container path, or
change the native workflow through free-form instructions.

Successful behavior is observable in the returned aggregated result, including
individual predictions, ensemble predictions, test metrics and the final report.
This Profile describes what to evaluate; it does not claim that the Agent passes.

## Behaviors to Test

- With a readable configured dataset, the Agent executes its native workflow and
  returns an aggregated forecast with per-model and ensemble metrics.
- When supported numeric parameters are supplied, the binding applies them only
  within its documented bounds. Missing parameters use the native defaults.
- The returned result includes per-slice data, the averaged aggregate and the
  final report produced by the public workflow.
- Missing datasets, malformed options, unsupported fields and out-of-range
  numeric values fail explicitly instead of producing a success-looking result.
- Errors from native execution propagate; the binding does not convert an
  execution failure into a forecast.
- Reported metrics correspond to returned predictions and reflect the selected
  time series.

## Deployment Integration

- The outer binding supplies the writable deployment output directory to native
  preprocessing and forecasting, and passes both validation and test data to
  forecasting. These argument repairs are integration overrides; upstream source
  files and forecasting algorithms remain unchanged.
- Deployment-only TSCI_DEPLOY_* variables can select bounded default numeric run
  settings. Explicit supported Case overrides still take precedence.
- Real model clients share a deployment call budget (24 by default), a per-call
  output cap (1024 tokens by default; TSCI_MODEL_OUTPUT_LIMIT), a 60000-character input limit, no automatic
  model retries and a 60-second request timeout. Optional TSCI_REASONING_EFFORT
  selects low/high/max. Budget exhaustion rejects an incomplete result.
- Provider-reported `finish_reason=length` stops subsequent model calls and fails
  the Case, including when a native node catches the initial truncation error.
  Structured-output parsing retains raw metadata for this check, then returns
  the normal parsed object (or the caller-requested raw result). Parsing errors
  propagate; no paid retry or limit increase is performed automatically.

## Known Limitations or Prohibited Behaviors

- The native workflow expects a CSV with a `date` timestamp column and an `OT`
  target column. Other schemas, multi-target forecasting and non-tabular inputs
  are not supported by this deployment.
- Case text is not forwarded to the five native agents as a natural-language
  instruction. Free-form prose triggers the configured workflow without
  changing its run parameters; use JSON or `key: value` lines for supported
  numeric overrides.
- The binding does not accept file uploads or arbitrary Case-supplied paths.
  Dataset selection is limited to the packaged ETTh1 sample or the operator-set
  `TSCI_DATA_PATH` inside the container.
- The workflow is the fixed LangGraph chain preprocess → analyze → validate →
  forecast → report. It has no dynamic tools, arbitrary code execution or human
  approval step.
- The binding writes outputs to a private temporary directory. Files are
  available during the Case and removed when the binding closes; state does not
  persist across Cases.
- Native "confidence intervals" use percentiles across model point predictions.
  With one model, or identical model forecasts, the intervals have zero width.
  These intervals are not demonstrated to have calibrated predictive coverage;
  evaluate their reported values rather than treating confidence labels as a
  guarantee. Upstream interval calculations remain unchanged.
- A deployment output cap can truncate model analysis. Known truncation is an
  explicit execution error, not a successful complete report. Missing finish
  metadata does not establish completeness.
- Model selection is LLM-driven and may vary between runs. Forecast accuracy is
  not guaranteed; report the observed outputs and metrics without claiming a
  target accuracy.
- Capabilities outside the deployed workflow, including retrieval, external
  services and arbitrary scripting, are not provided or verified.
- The Agent must not expose credentials, invent dataset facts, or claim work
  that the returned result does not show.

# TimeSeriesScientist integration

The source is acquired by ABB with `method="git"` at commit `41b396316fee25462c56cb53635b42660042d890`. Inner `agent/` is ignored runtime material, not part of this contribution. A clean source preparation restores and inventories the actual upstream files; no native graph descriptor is invented. The outer factory is `bindings/tsci_workflow.py:create_graph`.

The binding repairs missing orchestration arguments and applies bounded deployment execution without changing upstream source or forecasting algorithms. Model routes retain the native OpenAI-compatible protocol and are replaced by the runtime-selected provider; no provider credential is committed or fixed in the Agent manifest.

Deployment controls: `TSCI_MODEL_MAX_CALLS` (default24), `TSCI_MODEL_OUTPUT_LIMIT` (default1024, range128–4096), `TSCI_REASONING_EFFORT`, and bounded `TSCI_DEPLOY_*` numeric defaults. The output limit intentionally has a non-credential name: `TSCI_MODEL_MAX_TOKENS` would be classified as a secret by current ABB manifest generation. A Case cannot set these deployment controls or arbitrary file paths. Input/output limits, reported truncation, and structured parsing are tested in `tests/test_issue384.py`.

Upstream interval percentiles measure inter-model point-forecast spread. Single or identical model forecasts yield zero-width intervals. The independent no-network reproduction is in `evaluation/reproduce_reliability.py`; no calibrated coverage is claimed.

Current status is `adapting`, disabled for default benchmark selection. Current-main source preparation, configuration loading and offline checks do not constitute a current full container certification or official KUMA Evaluation. Historical custom local smoke results predate the final truncation guard. Paid model limits are not increased and repair calls are not triggered automatically.

# Offline reliability reproductions

These optional fixtures reproduce observed reliability failures. They do not change the KUMA Agent Profile schema, official Cases, local Judge criteria, or upstream forecasting algorithms.

`reproduce_reliability.py` requires the pinned TimeSeriesScientist source and its real image dependencies. Run it inside an existing compatible image with network disabled and the agent unit mounted at `/fixture`. It executes the native confidence-interval function on deterministic one-model, duplicated-model, and ordered two-model inputs, and checks the recorded six-point example against the packaged CSV. It makes no model/API calls. A passing reproduction confirms the named defect, not successful calibrated uncertainty.

The binding regression suite is `tests/test_issue237.py` in the ABB repository. It is self-contained and verifies output-directory wiring, numeric input contracts, SDK/call budgets, sync/async truncation handling, raw structured evidence, parsing-error propagation, and rejection after a native node catches a truncation error. These tests use fixtures; the real LangChain structured parser also receives a separate offline replay check.

The output cap remains 1024 tokens by default. A provider-reported `finish_reason=length` fails the Case and stops further model calls; it does not trigger paid repair/retry calls. Raising the cap is an explicit deployment decision. A missing finish reason is not treated as proof of output completeness.

Current evidence separates earlier paid local smokes from the updated guard's offline checks. No new official KUMA evaluation or current paid acceptance is implied.

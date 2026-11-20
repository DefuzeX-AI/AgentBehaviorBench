# Native execution configuration

ABB bindings preserve native execution limits. They must not lower them to fit a
benchmark timeout or invent a second graph/model-call budget. Run deadlines and
cancellation remain orchestration policy, separate from Agent configuration.

Precedence: explicit caller settings, then native effective settings / native
entrypoint defaults, then the native graph/framework default. Copy configuration
containers before modifying them; keep callback objects and thread identity intact.
APIs without a RunnableConfig parameter use LangChain's ambient config context;
this does not imply their non-LangChain internals consume every RunnableConfig field.
Native field validation and errors remain in force.

## Changes

- EvoScientist reads the native effective recursion limit; no construction-time 150 override.
- Local Deep Research uses native research/search budgets. Explicit native settings
  may be supplied as `configurable.settings_snapshot`.
- LabScript-AI reads max_attempts from its native public function signature; an
  explicit `configurable.max_attempts` wins. The pinned native streaming entrypoint's
  recursion limit 100 is retained with caller precedence, replacing the lower 50.
- Local RAG Researcher resolves its search count through native Configuration.
- Air-Lingjing omits max_steps unless explicitly configured. Native scenario
  termination remains authoritative; configurable.max_steps precedes the optional environment value.
- AI Hunter validates/defaults requests through the native HuntRequest model.
- TimeSeriesScientist keeps native slice counts, model clients, retries, output limits,
  request timeout and structured-output behavior. The shared call/input budget and
  truncation-triggered future-call rejection are removed. Secret env_vars snapshots
  remain excluded from model-facing configuration. Numeric requests remain positive
  integers without ABB-specific upper caps. Native algorithm validation still applies.
- CSGOTrading keeps the selected/all configured item list, without the four-item cap.
- GraphARC uses its native constructor default instead of 15. An explicit
  configurable.max_iterations applies only to that invocation; native minimum 1 is retained.
- JobSmith delegates default recursion policy to its compiled graph/framework.
- LambChat honors explicit recursion_limit instead of overwriting it.
- DeerFlow delegates omitted limits to its native client and preserves caller thread_id.

## Intentionally retained

Mini-opencode 100, LangChain Code's balanced-mode 45, Email Automation 100,
Sales Outreach 1000, Zeroapp's native two rounds, LangREPL's native configured
limit, and native retry/termination logic are not removed. The authored trajectory
fault lab is itself an Agent and retains its own 30 default.

Additional pinned-source checks confirmed that Multi-Agent-CAD's 50 is native:
https://github.com/Pan-Chera/Multi-Agent-CAD/blob/f31a2f65aa1b1e16fa6c45f1d642142fb696db28/multi_agent_cad/graph.py#L367

MedAgents' voting default 3 is likewise native, not an ABB restriction:
https://github.com/gersteinlab/MedAgents/blob/aaeff0499e169b41faf810cbca59504e3ee2788c/run.py#L18

The handbook no longer illustrates an arbitrary numeric deployment cap. Existing
Judge/GT artifacts, captured traces, timeout/cancellation and KUMA conversation
input counts are unchanged. Agent profiles describing removed limits are updated
for future runs; historical results are not rewritten.

## Validation and deployment

`python -m pytest -q tests/test_native_execution_configuration.py` exercises binding
calls with controlled native dependencies. It checks native defaults, caller overrides,
callbacks and thread propagation, unchanged input dictionaries, uncapped item batches,
and native clients surviving more than the old model-call budget. It does not call a
model, execute business tools or establish end-to-end Agent correctness.

Application synchronization must copy only the reviewed changes, retain platform
workspace adaptations, and migrate only unmodified installed bindings. Existing
frozen revisions/images retain their original code; subsequent builds need a new
source fingerprint. Never replace code inside an active container.

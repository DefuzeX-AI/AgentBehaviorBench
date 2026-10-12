# Saved execution configuration

Suite provenance records the model configuration used by each selected Agent.
For observe-mode Agents, `agent_models` contains declared, non-secret runtime
settings after manifest environment overrides. Unrelated replacement-provider
settings do not affect their recovery. For replace-mode Agents, it contains the
resolved target routing, including provider, endpoint, model and routing rules.
Credentials and declared secret environment variables are excluded.

`model_override` stores an explicit CLI model choice; `model` is only a summary
of a single default replacement target. Recovery resolves environment defaults
again, so changing an effective model or endpoint requires a linked new Suite
with reused Cases. Rotating a credential alone does not change provenance.

SDKs can implement `SDKExecutionConfiguration` to report public execution
settings. The local SDK uses its actual Judge resolver to record the Judge model
and endpoint separately, including explicit Judge overrides and fallback rules.

Reuse records configuration afresh for the selected Agents. Live reuse requests
share a batch only when their complete execution configuration matches,
including the selected Agents' model settings. Different Agent sets therefore
start separate batches rather than admitting settings absent from a saved plan.

Older plans lack native model provenance and cannot reliably establish the
original upstream. They remain readable and their saved Cases can be reused in
a new Suite; recovery must not silently backfill evidence from today's settings.

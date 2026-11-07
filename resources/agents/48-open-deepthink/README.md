# open-deepthink

Source: [iblameandrew/open-deepthink](https://github.com/iblameandrew/open-deepthink)
at `b440af10fd8fc9550b3a70fc76761465aede7a4b` (MIT; see `agent/LICENSE`).
Onboarding issue: [#221](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/221).
The pinned upstream source is restored into ignored `agent/` before execution.
`source-manifest.json` records its provenance. Do not commit the inner `agent/`
directory; `[source] method = "git"` restores the fixed revision on clean checkouts.

The binding invokes the public `deepthink.api.run_qnn` workflow. Plain text is
passed verbatim as `user_prompt`; `proposed_solution` is selected as the answer,
matching the native CLI. The complete native result is retained as raw evidence.
Each input is independent, without
conversation history, documents, web tools or code execution. QDAD, distillation
and the optional web UI are not exposed.

`agent.toml` explicitly sets the upstream QNN parameters to one layer, two
personas and two epochs in manual mode. This exercises persona updates and
synthesis with a bounded topology; it does not test multiple layers. Other
parameters retain upstream defaults. The runtime timeout is 1,800 seconds.

The binding propagates live RunnableConfig callbacks through LangChain's
configuration context without adding an unsupported keyword to `run_qnn`.
Each invocation owns and closes its synchronous and asynchronous HTTP clients,
including when the native workflow raises an error.

## Run

From the ABB repository root, with ABB and its SDK dependencies installed and
Docker available:

```bash
python -m agentbench evaluate open-deepthink --cases 1 --max-steps 1 --sdk local --no-view -y
```

Configure the host model service with `OPENROUTER_API_KEY`,
`OPENROUTER_BASE_URL` and `OPENROUTER_MODEL` in the repository `.env`.
The agent uses its native OpenRouter endpoint and an injected runtime credential;
ABB intercepts that route and forwards calls to the host-selected model service.
Do not forward real host keys or the school's endpoint into the agent image.
No additional tool-service credentials are needed.

After submitting the PR and obtaining KUMA Credit approval, run:

```bash
python -m agentbench evaluate open-deepthink --cases 1 --max-steps 1 --sdk kuma --no-view -y
```

Execution status, evidence completeness and Judge findings must be reported
separately. The upstream pipeline catches some intermediate errors; a final
report alone does not prove every model call succeeded. Full traces belong in
the designated submission storage, not this source directory.

## Reproduce configuration generation

For a DeepSeek-compatible endpoint that exhausts the default output budget in
reasoning, create `cache/onboarding-config/deepseek-build.toml`:

```toml
[build]
max_output_tokens = 32768
timeout_seconds = 300
thinking = "disabled"
```

Create `cache/onboarding-config/open-deepthink-context.json`:

```json
{"qnn_mode":"manual","manual_layers":1,"manual_width":2,"num_epochs":2}
```

```bash
python -m agentbench agent add https://github.com/iblameandrew/open-deepthink \
  -b --sdk kuma --no-view --agent-timeout 1800 \
  --build-settings cache/onboarding-config/deepseek-build.toml \
  --adapter-context cache/onboarding-config/open-deepthink-context.json
```

The thinking toggle affects configuration generation only. Its default is empty
and sends no provider-specific toggle. Reusing existing files may trigger fresh
source review; conflicts preserve the existing file for manual inspection.
Generated files require review: this integration's binding and profile were
subsequently refined to preserve callbacks, close clients and describe only the
deployed capabilities.

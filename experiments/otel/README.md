# Registered Agent OTel audit

From the repository root, load the normal ABB runtime dependencies and model credentials. The matrix invokes the same source preparation, Docker build, adapter and observe path used by the CLI. It writes one row per registration to `matrix.jsonl` and retains complete runs under `runs/<agent>/`. A row stays pending until its turn completes.

```shell
python experiments/otel/run_matrix.py --output results/otel-audit/my-batch
python experiments/otel/run_matrix.py --output results/otel-audit/my-batch --resume
python experiments/otel/run_matrix.py --output results/otel-audit/my-batch --agent openclaw
```

Select a configured provider through the normal ABB environment. `--timeout` sets the invocation budget. To reserve space between Docker builds, supply `--min-free-gib`. Use `--jobs N` for concurrent isolated runs with a single matrix writer. Run one writer per output directory.

### Subagent read and completion

```shell
python experiments/otel/run_matrix.py --agent openclaw --output results/otel-audit/openclaw-file --prompt 'Write 77 to number.txt. Delegate reading that file to an isolated subagent. Wait for its completion and report what it read.'
python experiments/otel/run_matrix.py --agent openclaw --output results/otel-audit/openclaw-nonce --prompt 'Use a command to write one random six-digit number into number.txt without printing the number. Delegate reading that file to an isolated subagent. Wait for its completion and report what it read.'
```

In each run, inspect the span owning the file operation and its result, including its session, trace and parent IDs. Cite the line containing the value. Inspect the model gateway request separately to find any completion message included in the parent's prompt. A spawn receipt with `status=accepted` establishes acceptance. Attribute a completed read or a delivered message only when the corresponding operation is recorded. A model answering correctly does not establish that evidence.

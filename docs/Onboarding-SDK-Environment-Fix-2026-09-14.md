# Preserve native service configuration during KUMA evaluation

New service-backed Agents declare database and endpoint settings in
runtime.env_keys. The previous evaluation overlay inserted a second env_keys
assignment, causing a TOML duplicate-key error before execution.

The overlay now merges the SDK variable names with the native list, deduplicates
names, and validates the complete parsed manifest against the intended change.
Secret-variable declarations and unrelated tables are preserved; the original
Agent manifest is never edited.

Validation: 63 focused SDK tests passed, with two opt-in tests skipped. The real
Docker/PyPI acceptance was then run separately and passed. It verified a native
environment setting inside the container and retained a Case, Agent output and
Judge report using offline providers and execution network disabled. No production
CaseGen, model or Judge service was called.

- SDK: kuma-defuzex 0.2.4 from PyPI.
- Image: defuzex-agentbench/kuma-pypi-acceptance:c8ebf02fd0650858b42c1e4b7f36a7e37942dcf18dbca3e92685d9f1bef2a965
- Evidence: results/verification/kuma-pypi-ee3dd21848734c3c9ddfa9116dac76de/
- package.json records native_environment_setting as preserved.
- case.json, agent-output.json, judge.json, run.json and verification.json retain
  the actual offline acceptance results.

The first verification attempt used an old local image tag that was no longer
present. It failed before container execution. The successful run used the
existing local ReAct image as its Python base and rebuilt the current overlay.

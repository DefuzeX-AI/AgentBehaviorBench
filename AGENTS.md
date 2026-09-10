Document how to adapt newly downloaded agents for inclusion in the benchmark.

Evaluation SDK integrations belong in `agentbench/sdk/<name>/`. Put shared
evaluation contracts/helpers in `sdk/contracts.py` and `sdk/common/`; keep
generic Docker and Agent execution in `runtime/`. `evaluation/` and
`sdk/kuma_runtime/` are compatibility imports, not implementation locations.
For SDK integration changes, run the SDK boundary/plugin tests and retain a
real container Run acceptance artifact with Case, Agent output and Judge.

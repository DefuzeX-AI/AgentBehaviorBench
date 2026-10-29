# Run from C:\Song_startup\benchmark\AgentBehaviorBench.
# All experiments use the same original GT prompt and model.
.\.venv\Scripts\python.exe -m agentbench evaluate verify561-before --registry tmp\verify-issue561-20261026-parallel\registry.toml --env-file .env --model openai/gpt-4.1-mini --sdk native --case-file tmp\verify-issue561-20261026-parallel\case.json --results-dir tmp\verify-issue561-20261026-parallel\before-results --no-view -y
.\.venv\Scripts\python.exe -m agentbench evaluate verify561-after --registry tmp\verify-issue561-20261026-parallel\registry.toml --env-file .env --model openai/gpt-4.1-mini --sdk native --case-file tmp\verify-issue561-20261026-parallel\case.json --results-dir tmp\verify-issue561-20261026-parallel\a --no-view -y
.\.venv\Scripts\python.exe tmp\verify-issue561-20261026-parallel\summarize.py


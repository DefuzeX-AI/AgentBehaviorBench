# BreadFree-Simu ABB integration

- Upstream: https://github.com/FeiCoder/BreadFree-Simu
- Revision: `6e5d9dde204728e5b93571c027a9030fb22eb94c`
- Upstream license: MIT (`agent/LICENSE`)
- Onboarding issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/217
- Framework: LangGraph
- Native graph: `breadfree.strategies.agent_strategy.build_graph`

The binding evaluates the upstream analyst → risk manager → fund manager graph. It accepts the
native graph's three required inputs and deliberately stops before the surrounding backtest strategy
parses the decision or sends simulated broker instructions.

Static validation:

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/48-breadfree-simu"), plugin))
PY
```

Runtime smoke command (requires Docker and a configured model service):

```bash
agentbench evaluate breadfree-simu --cases 1 --sdk local --no-view
```

# Multi-Drone Delivery

This case compares decentralized multi-drone delivery with a centralized policy while using the same scenario, environment, evaluator, and engine bridge.

```bash
python examples/full_case/run_case.py --help
python examples/full_case/run_case.py
```

The default command uses the mock engine. Configure the realtime bridge and an active `LJ-ENGINE` session to connect Unreal Engine.

Key files:

- `scenario.py`: scenario construction.
- `policy.py`: per-drone and centralized policies.
- `engines.py`: engine bridge implementations.
- `fake_engine.py`: deterministic test engine.
- `run_case.py`: executable entry point and result recording.

Without `AI_API_KEY`, the policy uses its deterministic fallback.

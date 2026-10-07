# Heterogeneous Fire Rescue

This case coordinates UAV reconnaissance with UGV firefighting through per-agent observations and explicit messages.

```bash
python examples/fire_rescue/run_case.py --help
python examples/fire_rescue/run_case.py
```

The default command uses the mock engine. A realtime run requires the matching Unreal scenario and active engine sessions.

Key files:

- `scenario.py`: assets, fire targets, and termination settings.
- `policy.py`: UAV search and UGV extinguishing policies.
- `engines.py`: mock and realtime bridge selection.
- `fake_engine.py`: deterministic test engine.
- `run_case.py`: executable entry point and result recording.

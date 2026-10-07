# Runnable Examples

[Project README](../../README.md) · [中文项目说明](../../README.zh-CN.md)

Run commands from `backend/` with the virtual environment active.

## Start Here

```bash
python examples/scenario_demo.py
```

This is the smallest end-to-end test and does not require Unreal Engine or an API key.

## Cases

| Case | Command | Engine |
| --- | --- | --- |
| Multi-drone delivery | `python examples/full_case/run_case.py --help` | Mock or realtime |
| Fire rescue | `python examples/fire_rescue/run_case.py --help` | Mock or realtime |
| Single-drone fire search | `python examples/singledrone_fire/run_case.py --help` | Realtime capable |
| Robot-dog navigation | `python examples/singledog/run_case.py --help` | Realtime capable |
| Heterogeneous delivery | `python examples/deliverytask/run_case.py --help` | Realtime capable |
| Bridge inspection | `python examples/bridge/run_case.py --help` | Realtime capable |
| Multi-car dispatch | `python examples/multicars/run_case.py --help` | Realtime capable |
| UAV-assisted robot dog | `python examples/uavdog/run_case.py --help` | Realtime capable |
| Mixed equipment tasks | `python examples/multiagentstasks/run_case.py --help` | Realtime capable |

## Engine Reference Client

```bash
python examples/ue_client/lj_engine_client.py --help
```

The client implements the `LJ-ENGINE` WebSocket contract and is useful for protocol testing before opening Unreal Editor.

## Generated Data

Examples may create `uploads/`, `results/`, logs, and SQLite records. These paths are ignored by Git and should not be published.

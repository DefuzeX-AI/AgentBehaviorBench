# LJ-ENGINE Reference Client

`lj_engine_client.py` is a Python implementation of the engine-side WebSocket contract. It can validate backend dispatch and acknowledgement handling without Unreal Engine.

## Connect

```bash
python examples/ue_client/lj_engine_client.py \
  --host 127.0.0.1 \
  --port 9909 \
  --address ue-test-01 \
  --profile delivery
```

The client connects to:

```text
ws://127.0.0.1:9909/ws/LJ-ENGINE/ue-test-01
```

Check the registered session:

```bash
curl http://127.0.0.1:9909/websocket/api/sessions
```

## Contract

The backend sends a JSON command with a command type, task identifier, and payload. The engine responds with an acknowledgement or execution result carrying the same task context. Environment bridges use these responses for `reset`, observation requests, and action completion.

Use `python examples/ue_client/lj_engine_client.py --help` to list profiles and options.

# LingJing Backend

[Project README](../README.md) · [中文项目说明](../README.zh-CN.md)

The backend is a FastAPI service for scenario management, multi-agent orchestration, Gym-style environment execution, Unreal Engine communication, model calls, and SQLite recording.

## Modules

| Path | Responsibility |
| --- | --- |
| `app/modules/agents/` | Agent definitions, LangGraph workflows, and policies |
| `app/modules/envs/` | Environments, episodes, evaluators, and engine bridges |
| `app/modules/engine_control/` | Scenario and action dispatch to engine sessions |
| `app/modules/realtime/` | WebSocket connections and session management |
| `app/modules/uav/` | Image upload, VLM analysis, and UAV compatibility APIs |
| `app/modules/simulation/` | Scenario, task, instance, and telemetry compatibility APIs |
| `app/modules/ai/` | OpenAI-compatible and Anthropic-compatible model clients |
| `app/db/` | SQLite models and session management |

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Python 3.10 or newer is required. Configure your own `AI_BASE_URL`, `AI_API_KEY`, model names, API style, and `INTERNAL_AI_TOKEN` in `.env`.

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 9909
```

Alternatively:

```bash
./scripts/deploy.sh bootstrap
./scripts/deploy.sh status
```

## Main Endpoints

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Health check |
| `GET /docs` | Swagger UI |
| `GET /api/agents` | Registered agent definitions |
| `GET /api/envs` | Registered environments |
| `POST /api/envs/{name}/episodes` | Create an episode |
| `POST /api/envs/episodes/{task_id}/step` | Execute one environment step |
| `GET /websocket/api/sessions` | Active WebSocket sessions |
| `WS /ws/LJ-ENGINE/{address}` | Engine connection |
| `POST /sim/engine/scenario` | Dispatch a scenario |
| `POST /sim/engine/command` | Dispatch a generic engine command |
| `POST /sim/vision/upload` | Upload and analyze an image |

## Mock Demo

```bash
python examples/scenario_demo.py
```

The demo starts a temporary backend and fake engine, then exercises scenario reset, observations, actions, episode execution, and SQLite recording.

## Tests

```bash
python -m pytest -q
python -m ruff check app examples tests
```

Runtime databases, logs, uploads, results, caches, and `.env` are excluded from version control.

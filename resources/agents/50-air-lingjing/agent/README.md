<div align="center">

# 🌐 LingJing Embodied Intelligence

**An open simulation stack for LLM-driven embodied agents in large 3D environments.**

<a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2563eb"></a>
<a href="./README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/语言-简体中文-dc2626"></a>

</div>

LingJing combines a FastAPI/LangGraph backend, runnable embodied-agent cases, and a Cesium-powered Unreal Engine 5.5 plugin in one repository. The backend handles task orchestration, LLM/VLM calls, Gym-style environment loops, engine communication, and data recording. The Unreal plugin provides the 3D world integration, heterogeneous equipment actors, cameras, UI, image capture, and telemetry.

Large Unreal assets are distributed separately through Hugging Face. This repository contains source code, configuration templates, tests, and compact example data only.

## 🗺️ Platform Overview

<p align="center">
  <img src="./docs/images/earth.png" alt="LingJing platform overview" width="95%">
</p>

LingJing connects heterogeneous simulators, geospatial assets, model services, and embodied agents through a shared urban physics environment. Each simulation step closes the perceive-think-act-communicate loop and records outputs for evaluation and visualization. [Open the high-resolution PDF](docs/figures/earth.pdf).

## 🧩 Runtime Framework

<p align="center">
  <img src="./docs/images/framework.png" alt="LingJing agent and simulation framework" width="95%">
</p>

The runtime separates agent policy, shared infrastructure, adjudication, command routing, evaluation, and simulation engines. This keeps policies independent from engine-specific protocols while preserving per-agent observations, message history, acknowledgements, and replayable trajectories. [Open the high-resolution PDF](docs/figures/framework.pdf).

## ✨ Highlights

- Multi-agent task orchestration with centralized, star, and broadcast coordination patterns.
- Gym-style `reset`, `step`, `run`, and `close` lifecycle with pluggable evaluators.
- OpenAI-compatible and Anthropic-compatible LLM/VLM providers.
- HTTP, WebSocket, and UDP integration with Unreal Engine.
- Cesium-based urban simulation with drones, vehicles, robot dogs, ships, and task actors.
- Mock engine support for backend development without Unreal Engine.

## Repository Layout

```text
LingJing-Embodied-Intelligence/
├── backend/
│   ├── app/                 # FastAPI application and runtime modules
│   ├── examples/            # Runnable cases and UE reference client
│   ├── tests/               # API, environment, and realtime tests
│   ├── scripts/             # Deployment and maintenance helpers
│   └── .env.example         # Safe configuration template
├── unreal/
│   └── EmbodyIntelligence/  # Unreal Engine 5.5 runtime plugin
├── docs/                    # README figures and high-resolution PDFs
├── ASSETS.md                # Hugging Face asset instructions
└── README.zh-CN.md          # Chinese documentation
```

## 🚀 Backend Quick Start

Requirements: Python 3.10 or newer.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Set your own provider values in `.env`:

```dotenv
AI_BASE_URL=https://api.example.com/v1
AI_API_KEY=replace-with-your-api-key
AI_CHAT_MODEL=replace-with-your-chat-model
AI_ANALYSIS_MODEL=replace-with-your-vision-model
AI_API_STYLE=openai
INTERNAL_AI_TOKEN=replace-with-a-long-random-token
```

Start the service:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 9909
```

Verify it:

```bash
curl http://127.0.0.1:9909/health
```

- Swagger UI: `http://127.0.0.1:9909/docs`
- Engine sessions: `http://127.0.0.1:9909/websocket/api/sessions`

Run the end-to-end mock demo without Unreal Engine or an API key:

```bash
python examples/scenario_demo.py
```

## 🧠 Runnable Cases

| Directory | Scenario |
| --- | --- |
| `examples/full_case/` | Multi-drone urban delivery and centralized baseline |
| `examples/fire_rescue/` | UAV reconnaissance with UGV firefighting |
| `examples/singledrone_fire/` | Closed-loop visual fire search |
| `examples/singledog/` | Robot-dog visual navigation |
| `examples/deliverytask/` | Heterogeneous delivery and route inspection |
| `examples/bridge/` | Bridge inspection from top-down and front views |
| `examples/multicars/` | Multi-vehicle dispatch and route-cost analysis |
| `examples/uavdog/` | UAV-assisted robot-dog navigation |
| `examples/multiagentstasks/` | Mixed equipment scenario dispatch |
| `examples/ue_client/` | Python reference implementation of an engine client |

See [backend/examples/README.md](backend/examples/README.md) for commands and runtime requirements.

## 🏙️ Unreal Engine Setup

Requirements:

- Unreal Engine 5.5.4
- Cesium for Unreal
- A host Unreal project
- The matching Hugging Face asset package

Install the plugin at:

```text
<HostProject>/Plugins/EmbodyIntelligence/
```

Download the asset repository:

```text
Coming soon / 即将上传
```

Install the downloaded asset package in its two mount locations:

```text
<HostProject>/Plugins/EmbodyIntelligence/Content/  # PluginContent
<HostProject>/Content/                            # HostContent
```

`Program` assets use the `/EmbodyIntelligence/...` plugin mount, while scene assets use the `/Game/ArtRes/...` host-project mount. See [ASSETS.md](ASSETS.md) and [unreal/EmbodyIntelligence/README.md](unreal/EmbodyIntelligence/README.md).

The plugin defaults to:

```text
ws://127.0.0.1:9909/ws/LJ-ENGINE/image
```

For a remote backend, update `WEBSOCKET_URL` in `Source/ue5project/Core/DataManager.cpp` before building.

## 🧪 Validation

```bash
cd backend
python -m pytest -q
python -m ruff check app examples tests
```

The Unreal plugin must be compiled in Unreal Engine 5.5.4 with Cesium enabled. Generated `Binaries/`, `Intermediate/`, logs, databases, uploads, and result folders are intentionally excluded from Git.

## Security

- Never commit `.env`, API keys, access tokens, databases, uploaded images, or runtime logs.
- Replace every placeholder in `.env.example` before deployment.
- Rotate any credential that has previously appeared in a source file or shared archive.
- Treat WebSocket logs and captured images as potentially sensitive data.
- Review third-party asset licenses before publishing the Hugging Face repository.

## GitHub Metadata

Suggested description:

> Open embodied-intelligence simulation stack with a FastAPI/LangGraph multi-agent backend, reproducible urban task cases, and a Cesium-powered Unreal Engine 5.5 plugin.

Suggested topics: `embodied-ai`, `multi-agent`, `unreal-engine`, `ue5`, `cesium`, `simulation`, `robotics`, `langgraph`, `fastapi`, `digital-twin`.

## License

No license is selected in this release package. Add a `LICENSE` file only after confirming the redistribution terms for the source code and all Unreal/Hugging Face assets.

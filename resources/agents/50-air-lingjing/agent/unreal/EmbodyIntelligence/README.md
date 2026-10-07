<div align="center">

# 🏙️ EmbodyIntelligence UE Plugin

<a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2563eb"></a>
<a href="./README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/语言-简体中文-dc2626"></a>

</div>

Runtime plugin for Unreal Engine 5.5.4 that connects Cesium-based 3D scenes to the LingJing backend. It provides equipment and task actors, cameras, image capture, Slate/UMG UI, WebSocket control, HTTP upload, and UDP telemetry.

## Requirements

- Unreal Engine 5.5.4
- Cesium for Unreal
- Enabled `DatasmithImporter`, `BlueprintFileUtils`, and `WebSocketNetworking` plugins
- Large assets from the matching Hugging Face asset release

## Install

From the monorepo root:

```bash
cp -a unreal/EmbodyIntelligence <HostProject>/Plugins/
```

The resulting path must be:

```text
<HostProject>/Plugins/EmbodyIntelligence/EmbodyIntelligence.uplugin
```

## 📦 Assets

Download:

```text
Coming soon / 即将上传
```

Copy `PluginContent/` into `<HostProject>/Plugins/EmbodyIntelligence/Content/` and `HostContent/` into `<HostProject>/Content/`. The source uses both `/EmbodyIntelligence/...` plugin paths and `/Game/ArtRes/...` host-project paths. See [../../ASSETS.md](../../ASSETS.md).

## Configure the Backend

The default endpoint is defined in `Source/ue5project/Core/DataManager.cpp`:

```cpp
#define WEBSOCKET_URL TEXT("ws://127.0.0.1:9909/ws/LJ-ENGINE/image")
```

Change the host before compiling when the backend runs on another machine. `ADataManager` also listens for UDP data on port `8802` by default.

## Build and Run

1. Close Unreal Editor.
2. Copy the plugin and host-project assets into their required locations.
3. Regenerate project files if required by your platform.
4. Build the host project for Unreal Engine 5.5.4.
5. Open the project and enable the plugin when prompted.
6. Start the LingJing backend on port `9909`.
7. Run PIE and verify the engine session at `/websocket/api/sessions`.

Generated `Binaries/`, `Intermediate/`, `Saved/`, IDE files, and large `Content/` assets are excluded from Git.

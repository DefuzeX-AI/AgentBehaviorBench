<div align="center">

# 🏙️ EmbodyIntelligence UE 插件

<a href="./README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2563eb"></a>
<a href="./README.zh-CN.md"><img alt="简体中文" src="https://img.shields.io/badge/语言-简体中文-dc2626"></a>

</div>

这是面向 Unreal Engine 5.5.4 的 Runtime 插件，用于连接基于 Cesium 的三维场景与 LingJing 后端。插件提供装备与任务 Actor、相机、图像采集、Slate/UMG UI、WebSocket 控制、HTTP 上传和 UDP 遥测。

## 依赖

- Unreal Engine 5.5.4
- Cesium for Unreal
- 启用 `DatasmithImporter`、`BlueprintFileUtils` 和 `WebSocketNetworking`
- 与源码版本匹配的 Hugging Face 大型资产包

## 安装

在 monorepo 根目录执行：

```bash
cp -a unreal/EmbodyIntelligence <HostProject>/Plugins/
```

最终路径应为：

```text
<HostProject>/Plugins/EmbodyIntelligence/EmbodyIntelligence.uplugin
```

## 📦 资产

下载地址：

```text
Coming soon / 即将上传
```

将 `PluginContent/` 复制到 `<HostProject>/Plugins/EmbodyIntelligence/Content/`，并将 `HostContent/` 复制到 `<HostProject>/Content/`。源码同时使用 `/EmbodyIntelligence/...` 插件路径与 `/Game/ArtRes/...` 宿主项目路径。详细说明见 [../../ASSETS.zh-CN.md](../../ASSETS.zh-CN.md)。

## 配置后端地址

默认地址位于 `Source/ue5project/Core/DataManager.cpp`：

```cpp
#define WEBSOCKET_URL TEXT("ws://127.0.0.1:9909/ws/LJ-ENGINE/image")
```

若后端在其他机器上，请在编译前修改主机地址。`ADataManager` 默认还会监听 UDP `8802` 端口。

## 编译与运行

1. 关闭 Unreal Editor。
2. 将插件和宿主项目资产复制到正确目录。
3. 必要时重新生成项目文件。
4. 使用 Unreal Engine 5.5.4 编译宿主项目。
5. 打开项目并按提示启用插件。
6. 在 `9909` 端口启动 LingJing 后端。
7. 运行 PIE，并在 `/websocket/api/sessions` 检查引擎会话。

Git 会忽略 `Binaries/`、`Intermediate/`、`Saved/`、IDE 文件和大型 `Content/` 资产。

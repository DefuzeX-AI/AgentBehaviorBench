# 📦 资产分发

<a href="./ASSETS.md"><strong>English</strong></a> · <a href="./ASSETS.zh-CN.md"><strong>简体中文</strong></a>

大型 Unreal 地图、蓝图、模型、材质、纹理、粒子、字体和其他二进制资产通过 Hugging Face 单独分发：

```text
Coming soon / 即将上传
```

资产上传完成后，将在这里补充公开 Hugging Face 地址和校验清单。

## 建议的资产仓库结构

```text
EmbodyIntelligence-Assets/
├── PluginContent/
│   └── Program/
├── HostContent/
│   └── ArtRes/
├── README.md
└── MANIFEST.sha256
```

## 下载

```text
Coming soon / 即将上传
```

若资产仓库提供 `MANIFEST.sha256`，请在安装前校验。

## 安装

关闭 Unreal Editor，并备份现有资产目录。将两类资产分别安装到对应的 Unreal 挂载点：

```text
HostProject/
├── HostProject.uproject
├── Content/                         # HostContent -> /Game
└── Plugins/
    └── EmbodyIntelligence/
        └── Content/                 # PluginContent -> /EmbodyIntelligence
```

Linux/macOS：

```bash
cp -a EmbodyIntelligence-Assets/PluginContent/. <HostProject>/Plugins/EmbodyIntelligence/Content/
cp -a EmbodyIntelligence-Assets/HostContent/. <HostProject>/Content/
```

PowerShell：

```powershell
Copy-Item `
  -Path .\EmbodyIntelligence-Assets\PluginContent\* `
  -Destination <HostProject>\Plugins\EmbodyIntelligence\Content\ `
  -Recurse -Force
Copy-Item `
  -Path .\EmbodyIntelligence-Assets\HostContent\* `
  -Destination <HostProject>\Content\ `
  -Recurse -Force
```

请勿混放两类资产：`PluginContent/Program` 对应 `/EmbodyIntelligence/Program`，`HostContent/ArtRes` 对应 `/Game/ArtRes`。

发布资产仓库前，应说明对应的源码版本、Unreal/Cesium 版本、校验值、第三方来源、许可证和再分发条件。

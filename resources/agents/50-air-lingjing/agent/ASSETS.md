# 📦 Asset Distribution

<a href="./ASSETS.md"><strong>English</strong></a> · <a href="./ASSETS.zh-CN.md"><strong>简体中文</strong></a>

Large Unreal maps, Blueprints, meshes, materials, textures, particles, fonts, and other binary assets are distributed separately through Hugging Face:

```text
Coming soon / 即将上传
```

The public Hugging Face URL and checksum manifest will be added here after upload.

## Recommended Asset Repository

```text
EmbodyIntelligence-Assets/
├── PluginContent/
│   └── Program/
├── HostContent/
│   └── ArtRes/
├── README.md
└── MANIFEST.sha256
```

## Download

```text
Coming soon / 即将上传
```

Verify `MANIFEST.sha256` if the asset repository provides it.

## Install

Close Unreal Editor and back up the existing content directories. Install each asset group at its matching Unreal mount point:

```text
HostProject/
├── HostProject.uproject
├── Content/                         # HostContent -> /Game
└── Plugins/
    └── EmbodyIntelligence/
        └── Content/                 # PluginContent -> /EmbodyIntelligence
```

Linux/macOS:

```bash
cp -a EmbodyIntelligence-Assets/PluginContent/. <HostProject>/Plugins/EmbodyIntelligence/Content/
cp -a EmbodyIntelligence-Assets/HostContent/. <HostProject>/Content/
```

PowerShell:

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

Keep the groups separate: `PluginContent/Program` resolves as `/EmbodyIntelligence/Program`, while `HostContent/ArtRes` resolves as `/Game/ArtRes`.

Before publishing the asset repository, document its matching source release, Unreal/Cesium versions, checksums, third-party sources, licenses, and redistribution terms.

# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — ワークフローを評価するアルパカ Agent" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  日本語 |
  <a href="README.zh-CN.md">中文简体</a> |
  <a href="README.zh-TW.md">中文繁體</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **ABB を実行する前に：**Python 3.10 以上、起動済みの Docker Desktop または
> Docker Engine を用意してください。KUMA は評価コンテナのビルド時に PyPI から自動で
> インストールされます。Company Research Agent には `KUMA_API_KEY`（または
> `DEFUZEX_API_KEY`）、`OPENROUTER_API_KEY`、`OPENROUTER_MODEL`、
> `TAVILY_API_KEY` が必要です。

AgentBehaviorBench は登録済み AI Agent を分離ランタイムで実行し、実行証跡を収集
して、選択可能な SDK で結果を評価します。既定 SDK は組み込み KUMA adapter です。
結果はローカルに保存され、ABB のブラウザビューアで確認できます。

![AgentBehaviorBench 実行アーキテクチャ](../figures/framework.png)

## クイックスタート

リポジトリのルートで仮想環境を作成し、ABB をインストール
します。

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

ローカル環境ファイルを作成し、資格情報を設定します。

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

Docker を起動してから、registry 内で `enabled = true` かつ `ready` のすべての
Agent を実行します。

```bash
agentbench run
```

ABB は選択された Agent の確認を求め、`results/` に結果スナップショットを保存して
ローカルビューアを起動します。ヘッドレスまたは自動実行では次を使います。

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

## 要件と環境変数

| 要件 | 用途 |
| --- | --- |
| Python 3.10 以上 | ABB ホスト CLI と harness。 |
| Docker Desktop / Docker Engine | 付属の ready Agent は Docker コンテナで実行されます。`run`、`evaluate`、`certify`、`observe` の前に Docker を起動してください。 |
| `KUMA_API_KEY` または `DEFUZEX_API_KEY` | 既定 KUMA SDK の Case と Judge へのアクセス。 |
| `OPENROUTER_API_KEY` | Docker Agent のモデル通信は ABB interceptor を経由して OpenRouter に送られます。 |
| `OPENROUTER_MODEL` | 実行に使用するモデル名。 |
| `TAVILY_API_KEY` | 付属 Company Research Agent の Web 検索資格情報。 |

`.env` は Git で無視されます。Shell ですでに export された変数は `.env` を上書きし、
`--env-file PATH` は別の dotenv ファイルを選択し、`--model MODEL` は一回のコマンド
だけモデルを上書きします。

任意の OpenRouter 設定：

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

インストール済みバージョンのヘルプは `agentbench --help` または
`agentbench <command> --help` で確認できます。

| コマンド | 用途 |
| --- | --- |
| `agentbench run` | 有効かつ `ready` の全 Agent を評価します。既定コマンドです。 |
| `agentbench evaluate company-research-agent --cases 1` | 指定数の独立した Case で 1 つの Agent を評価します。 |
| `agentbench observe company-research-agent` | ネイティブ入力で Agent を実行して trace を保存します。Case の作成や Judge 呼び出しは行いません。 |
| `agentbench certify react-agent` | `adapting` Agent を認定し、成功時に `ready` へ昇格します。 |
| `agentbench view results/benchmark.json` | 保存済み結果をローカルビューアで開きます。 |
| `agentbench sdk list` | 組み込みおよびインストール済み評価 SDK を一覧表示します。 |
| `agentbench clean --dry-run` | 復元可能なアーカイブへ移動されるローカル履歴を表示します。 |

よく使う `run` オプション：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

すべての引数は英語版の [CLI reference](../CLI.md) を、Agent の追加は
[agent onboarding guide](../How%20To%20Add%20Agent.md) を参照してください。

## リポジトリ構成

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

- `resources/registry.toml` は Agent、状態、runtime を宣言します。
- `resources/agents/` は各 Agent ユニットと ABB 設定を保持します。
- `agentbench/cli/` はターミナルコマンドを提供します。
- `agentbench/harness/` は suite 実行、結果、registry 読み込みを担当します。
- `agentbench/runtime/` はローカルまたは Docker で Agent を実行します。
- `agentbench/sdk/plugin/` は組み込み SDK adapter とプラグイン探索を含みます。

## 開発

```bash
python -m pytest
```

リポジトリの規約は [AGENTS.md](../../AGENTS.md) と [docs/AGENTS.md](../../AGENTS.md) を
参照してください。

## ライセンス

MIT。詳細は [LICENSE](../../LICENSE)。

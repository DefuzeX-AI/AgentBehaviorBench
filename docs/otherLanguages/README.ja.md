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
> Docker Engine、結果ビューアのビルドに使う Node.js 20.19 以上または 22.12 以上を
> 用意してください。KUMA は評価コンテナのビルド時に PyPI から自動でインストールされます。
> 付属の 2 つの Agent はどちらも `KUMA_API_KEY`（または `DEFUZEX_API_KEY`）、
> `OPENROUTER_API_KEY`、`OPENROUTER_MODEL`、`TAVILY_API_KEY` が必要です。

AgentBehaviorBench は登録済み AI Agent を分離ランタイムで実行し、実行証跡を収集
して、選択可能な SDK で結果を評価します。既定 SDK は組み込み KUMA adapter です。
結果はローカルに保存され、ABB のブラウザビューアで確認できます。

![AgentBehaviorBench 実行アーキテクチャ](../figures/framework.png)

初回実行でエラーが出た場合は、まず下の[トラブルシューティング](#トラブルシューティング)を
確認してください。

## クイックスタート

リポジトリのルートで仮想環境を作成し、ABB をインストール
します。

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

結果ビューアは `web/` からビルドし、ビルド成果物はリポジトリに含まれません。結果を開く前に
一度ビルドしてください。`run`、`evaluate`、`certify` は実行後にビューアを起動し、
`agentbench view` は保存済みの結果を再度開きます。

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
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

`KUMA_API_KEY` は KUMA SDK のドキュメントで使われる変数名です。ABB は別名
`DEFUZEX_API_KEY` も受け付けますが、`KUMA_API_KEY` が空のときだけ使います。
`OPENROUTER_MODEL` は必須で既定値はありません。上の値は例なので、自分のアカウントで
使えるモデルに置き換えてください。

Docker を起動します（`docker info` が成功すること）。リポジトリの registry では 2 つの
Agent が有効で、どちらも `ready` です：`react-agent` と `company-research-agent`。
まず 1 つの Case を評価します。これはキーに課金される KUMA の Case と Judge サービスを
呼び出します。

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

registry 内で `enabled = true` かつ `ready` のすべての Agent を実行します。

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
| Node.js 20.19 以上または 22.12 以上（npm を含む） | `web/` の結果ビューアを一度ビルドします。ヘッドレス実行（`--no-view`）には不要です。 |
| `KUMA_API_KEY` または `DEFUZEX_API_KEY` | 既定 KUMA SDK の Case と Judge へのアクセス。両方設定した場合は `KUMA_API_KEY` が使われます。 |
| `OPENROUTER_API_KEY` | Docker Agent のモデル通信は ABB interceptor を経由して OpenRouter に送られます。 |
| `OPENROUTER_MODEL` | 必須のモデル名。`.env.example` の値は例であり、実行時の既定値ではありません。アカウントで使えるモデルを選んでください。 |
| `TAVILY_API_KEY` | 付属の 2 つの Agent（ReAct と Company Research）の Web 検索資格情報。 |

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
`agentbench <command> --help` で確認できます。これがすべての引数のリファレンスです。

| コマンド | 用途 |
| --- | --- |
| `agentbench run` | 有効かつ `ready` の全 Agent を評価します。既定コマンドです。 |
| `agentbench evaluate company-research-agent --cases 1` | 指定数の独立した Case で 1 つの Agent を評価します。 |
| `agentbench observe company-research-agent` | ネイティブ入力で Agent を実行して trace を保存します。Case の作成や Judge 呼び出しは行いません。 |
| `agentbench certify NEW-AGENT` | `adapting` Agent を認定し、成功時に `ready` へ昇格します。 |
| `agentbench view results/benchmark.json` | 保存済み結果をローカルビューアで開きます（先に `web/` をビルド。クイックスタート参照）。 |
| `agentbench sdk list` | SDK adapter ディレクトリを、実装を import せずに一覧表示します。 |
| `agentbench clean --dry-run` | `clean` が `cache/history-trash/` へ移動する、`results/` 内の参照されていない項目を表示します。削除はしません。 |

よく使う `run` オプション：

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

Agent の追加（`agent add`）は[英語版 README の CLI 節](../../README.md#cli)（英語）と
[agent onboarding guide](../How%20To%20Add%20Agent.md)（英語）を参照してください。

## トラブルシューティング

初回実行で `evaluate`、`run`、`certify` が出力する主なエラーです。モデル名の行を除き、
いずれも KUMA へのリクエスト前に停止するため課金されません。

| 出力 | 原因 | 対処 |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker が起動していないか、`DOCKER_HOST` が存在しない daemon を指しています。 | `docker info` が成功するまで Docker Desktop または Docker サービスを起動します。 |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | 環境変数にも `.env` にも KUMA 資格情報がありません。 | `.env` に `KUMA_API_KEY` を設定します。 |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | 変数に KUMA 以外のキー（例：OpenRouter のキー）が入っています。 | KUMA 用に発行された `dfx_` キーを使います。 |
| `AuthenticationError: Invalid API key.`（直前に `GET defuzex.ai/… \| HTTP 401`） | KUMA キーが誤っている、失効している、または別の Backend 用です。 | キーを差し替えます。`KUMA_BASE_URL` を設定している場合はそれも確認します。 |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | `OPENROUTER_MODEL` が未設定です。ABB に既定モデルはありません。 | `.env` に `OPENROUTER_MODEL` を設定するか、`--model` を渡します。 |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY`（または `TAVILY_API_KEY`） | モデル上流または Agent の `agent.toml` が必要とする資格情報がありません。 | 表示された変数を `.env` に追加するか export します。 |
| `LLM call 01 \| openrouter \| FAILED` の後に、上流のメッセージを引用した `related network: upstream_error POST …` | モデル上流が呼び出しを拒否しました（存在しないモデル名、キーに権限がない等）。Case は生成済みで、Judge と課金は発生し得ます。 | 利用中のキーで上流が提供しているモデル名を使います。 |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | このチェックアウトでビューアがまだビルドされていません。 | Node.js 20.19 以上または 22.12 以上で表示されたコマンドを実行します。 |

`agentbench clean` は何も削除しません。`results/` 直下の参照されていない項目を表示し、
確認後に `cache/history-trash/<タイムスタンプ>/` へ移動します。保存済み Suite とそれが
参照する成果物はそのまま残ります。元に戻すには、実行とビューアを止めてから、アーカイブ
された項目を `results/` に戻します。

## リポジトリ構成

```text
AgentBehaviorBench/
├── resources/registry.toml
├── resources/agents/
├── agentbench/cli/
├── agentbench/harness/
├── agentbench/runtime/
├── agentbench/sdk/plugin/kuma/
├── web/
└── results/
```

- `resources/registry.toml` は Agent、状態、runtime を宣言します。
- `resources/agents/` は各 Agent ユニットと ABB 設定を保持します。
- `agentbench/cli/` はターミナルコマンドを提供します。
- `agentbench/harness/` は suite 実行、結果、registry 読み込みを担当します。
- `agentbench/runtime/` はローカルまたは Docker で Agent を実行します。
- `agentbench/sdk/plugin/` は組み込み SDK adapter とディレクトリ探索を含みます。
- `web/` は結果ビューアのソースです。`npm run build` が CLI の配信する `web/dist` を生成します。

実行の流れは `resources/registry.toml` → CLI での選択 → SuiteRunner／評価 SDK →
Agent adapter とランタイム → 結果スナップショットとローカルビューアです（上のアーキテクチャ図を参照）。

## 開発

```bash
python -m pytest
```

リポジトリの規約は [AGENTS.md](../../AGENTS.md)（英語）を参照してください。

## ライセンス

MIT。詳細は [LICENSE](../../LICENSE)。

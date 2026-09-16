# Agent の追加

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | 日本語 | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

**環境設定 → 追加コマンドの実行 → 生成ファイルの確認** の順に進めます。
ユーザーも coding agent も同じ手順を使えます。ディレクトリを変更する指示がない限り、
ABB リポジトリのルートでコマンドを実行してください。

## 1. 環境を設定する

### ABB とホスト側の依存関係

先に [ABB のインストール](README.ja.md) を済ませます。Git、Python 3.10+、有効な
仮想環境が必要です。認証には実行ユーザーがアクセスできる Docker も必要です。
選択した SDK のホスト側検証パッケージをインストールします。

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

sdk list に kuma が表示され、ABB と同じユーザーで docker info が成功することを確認します。
ダウンロードと設定生成だけなら Docker は不要ですが、-c の認証には必要です。
ホストと評価コンテナの SDK インストールは別です。

### 認証情報とモデル

.env が存在しない場合だけテンプレートをコピーします。

```bash
test -f .env || cp .env.example .env
```

ローカルで編集します。

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key**：戦略カタログ取得、Case 生成と Judge に必要です。ABB は DEFUZEX_API_KEY
  も受け付けますが、空でない KUMA_API_KEY が優先されます。
- **OpenRouter key とモデル**：接続設定ファイルの生成と Agent の実行に使います。
  生成用モデルには **厳密な構造化出力** の対応が必要です。通常のチャットが動くだけでは
  十分ではありません。例のモデル名は設定例であり、暗黙の実行時デフォルトではありません。
- **Agent 固有の依存関係**：上流の説明に従ってツール key、データ、外部サービスを用意します。
  DB ドライバーのインストールは DB の起動ではなく、Agent のダウンロードも全サービスの配備ではありません。

key の取得先は [設定ガイド（英語）](../../README.md#configure-a-real-evaluation) にあります。
シェルで export した変数が .env より優先され、--env-file PATH で別のファイルを指定できます。
CLI は宣言された認証情報を解決し、.env 全体をコンテナにマウントしません。
実際の key をソースや生成設定に記入しないでください。

### 必要ならビューアーを準備

npm と Node.js **20.x の 20.19 以上、または 22.12 以上** が必要です。

```bash
cd web
npm ci
npm run build
cd ..
```

これは ABB ビューアーのビルドです。Agent 自身のブラウザーや Node/MCP 依存関係は別です。
画面が不要なら以下の追加コマンドに --no-view を付けます。ヘッドレス実行には Node や web/dist は不要です。

## 2. 追加コマンドを実行する

URL を Agent の GitHub リポジトリに置き換えます。ファイルや /tree/branch の URL は使いません。

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`：接続設定を生成・検証し、adapting として登録します。Docker イメージの即時ビルドではありません。
- `-c`：認証フローで Agent をビルド・実行します。設定された Case の実行確認が成功すると ready になります。
  Judge が行動上の問題を報告する場合もあります。

ABB はソースを取得し、接続を計画し、各ファイルを検証・保存してから認証の確認を求めます。
生成と認証には料金が発生する場合があります。自動設定は現在 **LangGraph** をサポートします。
他のフレームワークには対応アダプターが必要です。

認証前に生成ファイルを確認するなら -c を省略します。

```bash
agentbench agent add https://github.com/owner/repository -b
```

両方のフラグを省略した agentbench agent add URL はダウンロードと設定ファイル一覧の出力のみで、
接続設定の生成や実行可能 Agent の登録はしません。デフォルトブランチの revision を記録します。
現在 --revision オプションはありません。

| オプション | 用途 |
| --- | --- |
| `--no-view` | ビューアーを起動せず認証。結果は保存します。 |
| `--build-model MODEL` | 接続設定の生成用モデル。 |
| `--model MODEL` | 認証時に Agent が使うモデル。 |
| `--answers answers.txt` | 前回の計画の質問へテキストで回答。 |
| `--with-observe` | -b と併用して observe のネイティブ入力プロンプトを生成。 |
| `--build-settings settings.toml` | [build] テーブルで生成設定を上書き。 |

生成モデルの優先順位は --build-model、設定ファイルの model、OPENROUTER_BUILD_MODEL、
OPENROUTER_MODEL です。予算・タイムアウト・再試行を変える前に
[既定の設定](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml) を確認してください。

## 3. 各ファイルの役割を理解する

Agent 単位のディレクトリは `resources/agents/NN-name/` です。取得したソースの周囲に
接続ファイルが生成されるので、実行前に全部を手書きする必要はありません。

```text
resources/agents/NN-name/
├── agent/                   # Downloaded upstream source
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 本体のソース

取得した上流リポジトリを保持します。実際のグラフ、推論、ツールはここに残します。
ABB の接続ファイルを外側に置き、統合時に元の動作を密かに置き換えないようにします。

### `agent.toml` — 起動と呼び出しの設定

ID、フレームワーク、ソース revision、Docker のビルド/起動、アダプター、入出力マッピング、
環境宣言、モデル/ツールの経路を定義します。エントリーポイントと必須入力を実装と照合します。
経路や変数の宣言だけではツール実装やサービス起動にはなりません。

### `bindings/*.py` — ネイティブ入出力との境界

同期・引数なしのファクトリーから実際の呼び出し可能 Agent を返します。ソースに基づく形式変換と
ライフサイクルの終了処理を担います。架空の回答や簡略化した別 Agent を使って合格させてはいけません。
Python 構文の妥当性だけではグラフが読み込めて実行できることは証明できません。

### `Dockerfile` — コンテナへのインストール

Python/システム依存関係を入れ、ソース、binding、設定をコピーします。CPU アーキテクチャ、
インタープリター、書き込み先、Agent 固有のブラウザー/Node 要件を確認します。
現在 KUMA overlay は python -m pip で SDK を入れるため、その Python に pip が必要です。

### `.dockerignore` — ビルドから除外するファイル

認証情報、ホストの venv、キャッシュ、結果を除外し、必要なソースと設定を残します。
-b が ABB テンプレートから生成します。

### `requirement.md` — 評価する内容

配備済み Agent の用途、観測可能な動作、実在するツール、制限を記述します。KUMA は YAML
front matter と Production Use Scenario、Behaviors to Test、Known Limitations or Prohibited
Behaviors の各節を要求します。戦略グループは現在の SDK カタログから選びます。

将来の拡張でなく現在の能力を書きます。検索専用 Agent は計算を説明できますが、サンプラーの
実行やファイル保存はできません。能力や入力が不足した場合の対処も明記します。
Profile は評価指針であり、ツール追加・システムプロンプト変更・保存済み Case の変更はしません。

### `evaluation/` — 任意の補助ファイル

Profile が schema や fixture を参照する場合だけ必要です。必須ディレクトリでもなく、
input-contract.json も必須ではありません。現在の公式 KUMA 生成経路はテキスト入力です。
構造化 schema がローカルで有効でもリモート対応の証明にはなりません。
ネイティブのマッピングは agent.toml と binding が担当します。

### レジストリーと自動記録

単位ディレクトリ外の resources/registry.toml がパス、有効化、adapting/ready、case 数を保存します。
生成後は adapting、認証が昇格を管理し、run は有効な ready Agent を選択します。

ダウンローダーは再利用のためにリポジトリと revision を記す **source-manifest.json を自動生成**します。
これは ABB 内部記録であり、KUMA 必須ファイルやユーザーが準備する文書ではありません。継続時は保持します。

生成履歴は別の `cache/onboarding/<unit-name>-<path-digest>/` にあります。
build-state.json は再利用可能な作業を追跡し、各 attempt に計画、SDK カタログ、steps、
build-result.json を保存します。これらも自動記録で、Agent 本体のソースではありません。

## 生成後

-b のみなら、binding に合うネイティブ入力 JSON を用意し、実行確認と認証を行います。

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

生成された Agent ID を使います。observe は KUMA の Case/Judge を使いませんが、モデル/ツールは
課金される場合があります。evaluate --cases 1 はレジストリーの数を変えません。certify はその数で
実行するので事前確認してください。すでに ready なら再認証せず戻ります。変更の検証には evaluate を使います。

生成が停止したら build-result.json と失敗した steps を読み、修正して同じ -b を再実行します。
完成ファイルは保持・再検証され、手動ファイルの競合は上書きせず停止します。
計画への補足情報は --answers answers.txt で指定できます。

[トラブルシューティング（英語）](../Troubleshooting.md)、[既知の問題（英語）](../Documentation-Issue-Audit.md)、
[開発者ガイド（英語）](../../agentbench/onboarding/build_agent_env/README.md) も参照してください。

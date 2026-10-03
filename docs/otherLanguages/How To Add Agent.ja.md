# Agent の追加

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | 日本語 | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

[ABB の起動方法 — 英語](../Guide.md) · [CLI リファレンス](cli.ja.md) · [登録表](Registry.ja.md)

ABB リポジトリのルートで仮想環境を有効にし、環境設定、ソースのインポート、統合ファイルの生成、確認、テストの順に進めます。SOURCE、AGENT_ID、NN-name、結果パスは実際の値に置き換えてください。

## 1. 環境を設定する

Git と Python 3.10+ を用意し、上記の起動ガイドで ABB をインストールします。Agent の実行と認証には、そのユーザーで利用できる Docker が必要です。KUMA による生成・検証では ABB と同じ仮想環境に KUMA をインストールします。

```bash
python -m pip install -e .
python -m pip install "kuma-defuzex[otel]>=0.3.3"
git --version
agentbench --help
agentbench sdk list
docker info
```

`sdk list` はプラグインを一覧するだけで、依存関係の検証ではありません。インポートと設定生成には Docker は不要です。ホストとコンテナの SDK インストールは別です。

`.env` がない場合のみ `.env.example` をコピーし、ローカルで編集します。KUMA には KUMA_API_KEY（または DEFUZEX_API_KEY）が必要です。設定生成は OpenRouter と厳密な構造化出力に対応するモデルを使います。

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate generation model:
# OPENROUTER_BUILD_MODEL=
```

対象 Agent の実行モデルは別設定です。LangGraph は OpenRouter、DeepSeek、GLM を利用でき、ネイティブ ACP は各 Agent のサービス認証情報を使います。起動ガイドを参照してください。`--build-model` は生成モデル、`--model` は認証時の ABB 置換先モデルです。シェルの変数が `.env` より優先されます。キーをソースや生成ファイルに書かないでください。

Web ビューアーには npm と Node.js 20.x の 20.19 以上、または 22.12 以上が必要です。フロントエンドをビルドしてください。`--no-view` の評価には Node や `web/dist` は不要です。

```bash
cd web
npm ci
npm run build
cd ..
```

## 2. ソースのインポートと設定生成

SOURCE は HTTPS の GitHub リポジトリ URL（ファイル・ブランチページは不可）、またはローカルの絶対ディレクトリです。GitHub は既定ブランチを使い、`--revision` はありません。ローカルでは `.git` を除外して内容のダイジェストを記録します。まずインポートします。

```bash
agentbench agent add https://github.com/owner/repository
```

次に同じソースで統合ファイルを生成します。`-b`・`-c` なしの再インポートは重複エラーになり、これらの指定で既存ユニットを再利用します。変更したソースからの更新は行いません。ローカルでは `/absolute/path/to/local-agent`、PowerShell では `"C:\work\local-agent"` を指定できます。

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma
```

`-b` は LangGraph と ACP に対応し、ファイルを生成・検証して `adapting` として登録します。Docker はビルドしません。KUMA は計画前に現行戦略カタログを取得します。同梱の `local` には統合検証 API がないため、生成には KUMA を使います。質問があれば実際のデプロイ情報を UTF-8 の `answers.txt` に書き、`--answers answers.txt` を付けて再実行します。有効な完了ファイルは保持されるため、失敗時は先に `build-result.json` を確認してください。

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma --answers answers.txt
```

## 3. 各ファイルの役割

Agent 単位のディレクトリは `resources/agents/NN-name/` です。取得したソースの周囲に
接続ファイルが生成されるので、実行前に全部を手書きする必要はありません。

```text
resources/agents/NN-name/
├── agent/                   # インポートした上流またはローカルのソーススナップショット
├── agent.toml               # ABB execution configuration
├── bindings/                # LangGraph binding; not required for native ACP
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

### `bindings/*.py`

LangGraph の binding は同期・引数なしファクトリーで実際の Agent を返し、入出力と終了処理を適合します。ACP は `agent.toml` のネイティブコマンドとプロトコルで動作し、Python binding のファクトリーは不要です。Agent 本来の動作を保持してください。

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

## 4. 設定の確認と検証

実際のソースと照合し、入口、入出力、依存関係、認証情報の宣言、モデル・ツールの経路を確認します。LangGraph はグラフ記述とファクトリー、ACP はネイティブコマンドとセッションを確認します。Profile には実装済みツール、必要な入力、制限を記載します。手動変更後は検証します（Bash の例）。

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/NN-name"), plugin))
PY
```

ファイルと SDK パーサーを確認し、Agent は実行しません。カタログ文脈がない場合、現行のリモートカタログ検証は行いません。静的検証だけでは実行成功を証明できません。

## 5. local スモーク Case を実行する

登録表で新 Agent を `enabled = true` にして、一つの Case を実行します。`local` は一般的なテキスト Cases とローカル Judge を使い、KUMA 後端のクレジットは消費しません。Agent と Judge のモデル呼び出しには料金が発生する場合があります。統合認証や KUMA の行動評価にはなりません。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

## 6. KUMA で評価する

スモークテスト後、KUMA で新しい Case を生成し、証拠収集と Judge レポート取得を行います。設定したモデルサービスと KUMA API を呼び出します。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

## 7. 結果を確認する

`Result saved` に表示された実際のファイルを使い、完全な `View:` URL を開いてコマンドを動かし続けます。Conversation は入出力、Judge は指摘、Timing は実行と OTel を表示します。実行完了と判定は別です。`issue` は指摘、`insufficient_evidence` だけでは確認済み欠陥を意味しません。

```bash
agentbench view results/suites/SUITE_ID/events.json
```

## 8. 統合を認証する

`adapting` の Agent を `run` 対象にするには有効状態で認証します。登録表の Case 予算で新たに実行し、過去の結果を承認する操作ではありません。全 Cases が呼び出しエラーなく完了すれば、Judge の指摘があっても `ready` になります。既に ready の Agent は再実行しないため、後のテストには `evaluate` を使います。`agent add -c` は有効な統合ファイルが必要で、`-b` を暗黙には有効にしません。

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
```

## 9. 結果、再実行、トラブル対処

計画、Cases、イベントは `results/suites/SUITE_ID/`、実行詳細は通常 `results/observe/RUN_ID/` に保存します。表示されたパスを使ってください。`--results-dir DIR` は ABB の結果ルート、`evaluate --output DIR` は別の SDK 成果物保存先です。

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view --results-dir results/my-run
```

`resume` は復旧可能な未完了作業、`retry` は一つの未完了 Case を対象にします。`reuse` は保存入力を新たに実行・判定し、元の結果を保持します。番号は 1 からです。ビューアーの Rerun this Case と Open reuse Suite も利用できます。バッチの所有プロセスを動かし続けてください。安全でない再実行や応答不明の要求は復旧できない場合があります。

```bash
agentbench resume results/suites/SUITE_ID
agentbench retry results/suites/SUITE_ID --agent AGENT_ID --case 1
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 1
```

Export JSON はスナップショットで、全トレースや独立 HTML ではありません。完全な証拠には Suite と参照先の実行ディレクトリを保持します。`agentbench clean --dry-run` で確認し、実際のアーカイブ前に実行とビューアーを停止します。

Trace UI not built は `web/` をビルドします。Docker エラーは同じユーザーで `docker info`、SDK インポートエラーは ABB の仮想環境への SDK インストールを確認します。モデル・キーはサービス、モデル名、シェル変数優先順位を確認します。計画エラーや needs_input は保存記録と実際の情報を確認します。

[CLI リファレンス](cli.ja.md) · [詳しいトラブル対処 — 英語](../Troubleshooting.md)

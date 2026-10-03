# ABB CLI リファレンス

[English](../cli.md) | [中文](cli.zh-CN.md) | [Français](cli.fr.md) | 日本語 | [한국어](cli.ko.md)

[README に戻る](README.ja.md) · [ABB の起動方法 — 英語](../Guide.md) · [Agent 登録表](Registry.ja.md) · [Agent を追加する方法](How%20To%20Add%20Agent.ja.md)

各コマンドの目的、公開引数のすべて、既定の動作、使用例を説明します。実行前に ABB のインストールと対象 Agent の設定を完了してください。

AGENT_ID、SUITE_ID、CASE_ID、RUN_ID、ソースパス、ファイル名は実際の値に置き換えます。Agent 番号は表示一覧に対応し、Case 番号は 1 から始まります。OPTIONS は各表のオプションです。全コマンドが -h/--help に対応し、引数なしの agentbench は run を実行します。

```bash
agentbench --help
agentbench evaluate --help
agentbench agent add --help
```

agent は add、sdk は list または show のサブコマンド指定が必要です。グループのヘルプは agentbench agent --help または agentbench sdk --help。グループ階層ではサブコマンド指定前に -h/--help のみ使えます。

## コマンドを選ぶ

| コマンド | 目的と既定の動作 |
| --- | --- |
| `agentbench run` | 登録表の有効かつ ready の Agents を一つの Suite で実行します。各 case 数・step 予算を使い、実行前に選択を確認します。 |
| `agentbench evaluate` | 有効な Agent 一つについて、SDK で独立した Cases を生成し、実行・証拠収集・Judge 判定を行います。certify と異なり登録状態を変更しません。 |
| `agentbench agent add` | GitHub リポジトリまたはローカルディレクトリをインポートします。-b/-c なしではソースの取り込みと一覧表示のみ。-b は設定生成、-c は認証で、併用できます。 |
| `agentbench certify` | 有効な adapting Agent の登録済み Case 予算を実行し、全 Cases が呼び出しエラーなく完了すると ready にします。Judge の問題指摘だけでは昇格を妨げません。ready は再実行しません。 |
| `agentbench observe` | 一つのネイティブ入力を実行し、出力とトレースを保存します。SDK の Case 生成と Judge は使いません。現在は Docker の oneshot 実行が必要です。--list と --show は読み取りのみです。 |
| `agentbench view` | 保存済み結果をローカル Web ビューアーで表示します。先に Web をビルドし、表示された View URL 全体を開いてコマンドを動かし続けます。Ctrl+C で停止します。 |
| `agentbench sdk list` | SDK ディレクトリから発見したプラグイン名を一覧表示します。全実行依存関係のインストールを確認するものではありません。 |
| `agentbench sdk show` | SDK プラグインを読み込み、保存元・実行方式・暗黙選択の可否を表示します。 |
| `agentbench resume` | 保存済み Cases・設定と現在の認証情報を使い、Suite の復旧可能な未完了作業を再開します。新しい Cases は生成せず、完了済みを意図的に再実行しません。 |
| `agentbench retry` | 元 Suite の未完了 Case 一つを元入力で復旧します。保存状態によりリクエストを再開するか、最初の入力から再実行します。再実行条件は引き続き適用されます。 |
| `agentbench reuse` | 保存した Case 入力で新しい Agent 実行・証拠収集・Judge 判定を行い、関連する再実行 Suite に保存します。元結果を維持し、新入力は生成しません。完了 Case の再実行に使います。 |
| `agentbench clean` | プロジェクト results の未参照のトップレベル履歴を cache/history-trash に移し、保存 Suites と参照成果物を維持します。先に確認し、実際の整理前に実行とビューアーを停止します。 |

## `run`

登録表の有効かつ ready の Agents を一つの Suite で実行します。各 case 数・step 予算を使い、実行前に選択を確認します。

```text
agentbench run [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `--sdk NAME` | sdk list のディレクトリ名で SDK を選択します。同梱の既定は kuma、local は明示指定が必要です。暗黙選択可能なプラグインが複数ある場合も明示します。 | `--sdk kuma` |
| `--sdk-options PATH` | 選択した SDK のオプションを JSON オブジェクトから読み込みます。省略時は SDK の既定値を使います。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全に復旧可能な Case 失敗への追加自動試行回数です。0 以上の整数、既定は 2。0 で自動再試行を無効にします。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 最初の再試行までの待機秒数です。有限の非負数、既定は 5。その後の待機時間は再試行方針に従って増えます。 | `--retry-delay 5` |
| `-y, --yes` | 実行の確認を省略します。既定では確認します。 | `--yes` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--results-dir DIR` | ABB の結果ルートを指定し、なければ作成します。リポジトリルートでの既定は results/ です。イベントは DIR/suites/SUITE_ID/events.json に保存されます。旧保存先オプションとは併用できません。 | `--results-dir results/my-run` |
| `--output PATH` | 旧 ABB 保存先です。ファイル名を指定しても親ディレクトリを選ぶだけで、そのファイルは作成しません。--results-dir を推奨します。リポジトリルートでは既定は results/ です。 | `--output results/legacy.json` |
| `--no-view` | 結果を保存し、ビューアーを起動しません。既定では起動または再利用するため、ビルド済みの Web リソースが必要です。 | `--no-view` |
| `--model MODEL` | ABB の置換先モデルを上書きします。既定は選択したサービスの設定です。ネイティブ ACP のモデルは Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | ストリーミング時の旧メモリ一時保存しきい値です。単位はバイト、既定は 262144（256 KiB）。保存内容を切り詰めません。 | `--llm-trace-max-bytes 262144` |

run に --registry、--cases、--max-steps はありません。Agent ごとの既定予算は登録表で変更し、SDK JSON の max_steps でステップ予算を上書きできます。

### 使用例

```bash
agentbench run --sdk kuma
agentbench run --sdk local --yes --no-view --results-dir results/smoke
```

## `evaluate`

有効な Agent 一つについて、SDK で独立した Cases を生成し、実行・証拠収集・Judge 判定を行います。certify と異なり登録状態を変更しません。

```text
agentbench evaluate [AGENT] [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `-y, --yes` | 実行の確認を省略します。既定では確認します。 | `--yes` |
| `AGENT` | 有効な Agent の ID または一覧番号です。省略時は対話選択、--yes 使用時は指定必須です。ready 状態は必須ではありません。 | `react-agent` |
| `--registry PATH` | Agent 登録表を指定します。既定はプロジェクトの resources/registry.toml です。 | `--registry resources/registry.toml` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--model MODEL` | ABB の置換先モデルを上書きします。既定は選択したサービスの設定です。ネイティブ ACP のモデルは Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--sdk NAME` | sdk list のディレクトリ名で SDK を選択します。同梱の既定は kuma、local は明示指定が必要です。暗黙選択可能なプラグインが複数ある場合も明示します。 | `--sdk kuma` |
| `--sdk-options PATH` | 選択した SDK のオプションを JSON オブジェクトから読み込みます。省略時は SDK の既定値を使います。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全に復旧可能な Case 失敗への追加自動試行回数です。0 以上の整数、既定は 2。0 で自動再試行を無効にします。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 最初の再試行までの待機秒数です。有限の非負数、既定は 5。その後の待機時間は再試行方針に従って増えます。 | `--retry-delay 5` |
| `--no-view` | 結果を保存し、ビューアーを起動しません。既定では起動または再利用するため、ビルド済みの Web リソースが必要です。 | `--no-view` |
| `--llm-trace-max-bytes BYTES` | ストリーミング時の旧メモリ一時保存しきい値です。単位はバイト、既定は 262144（256 KiB）。保存内容を切り詰めません。 | `--llm-trace-max-bytes 262144` |
| `--results-dir DIR` | ABB の結果ルートを指定し、なければ作成します。リポジトリルートでの既定は results/ です。イベントは DIR/suites/SUITE_ID/events.json に保存されます。旧保存先オプションとは併用できません。 | `--results-dir results/my-run` |
| `--result-output PATH` | 旧 ABB 保存先です。指定ファイルを作らず、親ディレクトリを選びます。--results-dir を推奨し、両者は併用できません。既定はプロジェクトの results/ です。 | `--result-output results/legacy.json` |
| `--output DIR` | SDK 成果物の保存先です。ABB Suite の結果とは独立し、SDK JSON の output を上書きします。KUMA/local の既定は results/observe です。 | `--output results/sdk-artifacts` |
| `--timeout SECONDS` | SDK 実行のタイムアウト秒数で、有限の正数です。SDK JSON の timeout を上書きします。KUMA/local の既定は 2400、他の SDK は独自に定義します。 | `--timeout 2400` |
| `--cases N` | 独立した Cases の数で、正の整数です。既定は登録表の case。この実行だけ上書きし、登録表は変更しません。 | `--cases 1` |
| `--max-steps N` | Case ごとの SDK 対話ステップ上限で、正の整数です。登録表の step と SDK JSON の max_steps を上書きします。単一ステップのみ対応する Agent もあります。 | `--max-steps 3` |

### 使用例

```bash
agentbench evaluate react-agent --sdk kuma --cases 1
agentbench evaluate react-agent --sdk local --cases 1 --yes --no-view --results-dir results/smoke
agentbench evaluate react-agent --sdk kuma --cases 2 --max-steps 3 --output results/sdk-artifacts --results-dir results/my-run --no-view
```

## `agent add`

GitHub リポジトリまたはローカルディレクトリをインポートします。-b/-c なしではソースの取り込みと一覧表示のみ。-b は設定生成、-c は認証で、併用できます。

```text
agentbench agent add SOURCE [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `SOURCE` | HTTPS GitHub リポジトリ URL またはローカルの絶対ディレクトリを指定します。ブランチ・ファイル URL は不可です。通常は新規インポート、-b/-c は一致する既存ソースを再利用できます。 | `https://github.com/langchain-ai/react-agent` |
| `--agents-dir DIR` | 番号付き Agent 単位の親ディレクトリです。既定はプロジェクトの標準登録表に対応する resources/agents。生成先は --registry のルート内に置きます。 | `--agents-dir resources/agents` |
| `-b, --build` | 接続設定を生成・検証・保存し、adapting として登録します。有効な生成済みファイルを再利用します。LangGraph と ACP に対応し、Docker はビルドしません。既定は無効です。 | `-b` |
| `-c, --certify` | 生成済みまたは手動準備した設定を検証・登録し、認証します。-b は自動で有効になりません。既定は無効です。 | `-c` |
| `--registry PATH` | Agent 登録表を指定します。既定はプロジェクトの resources/registry.toml です。 | `--registry resources/registry.toml` |
| `--build-settings PATH` | [build] テーブルを含む TOML ファイルで生成予算・モデルなどを上書きします。既定は同梱設定。-b と併用します。 | `--build-settings build-settings.toml` |
| `--build-model MODEL` | -b の設定生成用 OpenRouter モデルです。優先順は本指定、[build].model、OPENROUTER_BUILD_MODEL、OPENROUTER_MODEL。構造化出力への対応が必要です。 | `--build-model openai/gpt-4.1-mini` |
| `--answers PATH` | 前回の生成計画の質問への回答を UTF-8 テキストで指定し、-b を再実行します。既定では回答ファイルを使いません。 | `--answers answers.txt` |
| `--with-observe` | -b 使用時に observe の対話入力フィールドを生成します。既定は無効、-b なしでは指定できません。 | `--with-observe` |
| `--agent-timeout SECONDS` | -b 使用時に生成する Agent の実行タイムアウトを設定します。有限の正数の秒、既定は 300。生成リクエストのタイムアウトではありません。 | `--agent-timeout 600` |
| `--adapter-context PATH` | -b 使用時に明示的なデプロイコンテキストの JSON オブジェクトを読み込みます。最大 64 KiB、既定では上書きしません。内容は Agent の接続方法に合わせます。 | `--adapter-context adapter-context.json` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--model MODEL` | -c 認証時の置換先モデルです。--build-model とは独立し、既定はサービス設定です。ネイティブ ACP のモデルは Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--output PATH` | -c の認証結果保存先です。管理 Suite では指定ファイルを作らず親ディレクトリを選びます。既定はプロジェクトの results/。このコマンドには --results-dir はありません。 | `--output results/add-certification.json` |
| `--no-view` | -c 使用時に認証結果を保存し、ビューアーを起動しません。インポートや設定生成には影響しません。既定では認証時に起動します。 | `--no-view` |
| `-y, --yes` | -c 認証の実行確認を省略します。既定では確認し、生成計画の質問に自動回答はしません。 | `--yes` |
| `--sdk NAME` | sdk list のディレクトリ名で SDK を選択します。同梱の既定は kuma、local は明示指定が必要です。暗黙選択可能なプラグインが複数ある場合も明示します。 | `--sdk kuma` |
| `--sdk-options PATH` | SDK オプションの JSON オブジェクトを読み込みます。-c の認証のみで使用し、-b の生成には適用しません。省略時は SDK の既定値です。 | `--sdk-options sdk-options.json` |

ローカルパスは絶対パスを使い、Windows では "C:\work\local-agent" と指定できます。-d は不可です。生成には OpenRouter と接続検証 API を持つ SDK が必要で、同梱 local は提供しません。

### 使用例

```bash
agentbench agent add https://github.com/langchain-ai/react-agent
agentbench agent add /absolute/path/to/local-agent -b --sdk kuma --build-model openai/gpt-4.1-mini
agentbench agent add /absolute/path/to/local-agent -b -c --sdk kuma --no-view
```

## `certify`

有効な adapting Agent の登録済み Case 予算を実行し、全 Cases が呼び出しエラーなく完了すると ready にします。Judge の問題指摘だけでは昇格を妨げません。ready は再実行しません。

```text
agentbench certify AGENT_ID [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `-y, --yes` | 実行の確認を省略します。既定では確認します。 | `--yes` |
| `--registry PATH` | Agent 登録表を指定します。既定はプロジェクトの resources/registry.toml です。 | `--registry resources/registry.toml` |
| `--sdk NAME` | sdk list のディレクトリ名で SDK を選択します。同梱の既定は kuma、local は明示指定が必要です。暗黙選択可能なプラグインが複数ある場合も明示します。 | `--sdk kuma` |
| `--sdk-options PATH` | 選択した SDK のオプションを JSON オブジェクトから読み込みます。省略時は SDK の既定値を使います。 | `--sdk-options sdk-options.json` |
| `--case-retries N` | 安全に復旧可能な Case 失敗への追加自動試行回数です。0 以上の整数、既定は 2。0 で自動再試行を無効にします。 | `--case-retries 0` |
| `--retry-delay SECONDS` | 最初の再試行までの待機秒数です。有限の非負数、既定は 5。その後の待機時間は再試行方針に従って増えます。 | `--retry-delay 5` |
| `--no-view` | 結果を保存し、ビューアーを起動しません。既定では起動または再利用するため、ビルド済みの Web リソースが必要です。 | `--no-view` |
| `AGENT_ID` | 有効かつ登録済み Agent の正確な ID を指定します。adapting を認証し、ready は再実行せず終了します。 | `folder-mover-agent` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--results-dir DIR` | ABB の結果ルートを指定し、なければ作成します。リポジトリルートでの既定は results/ です。イベントは DIR/suites/SUITE_ID/events.json に保存されます。旧保存先オプションとは併用できません。 | `--results-dir results/my-run` |
| `--output PATH` | 旧 ABB 保存先です。ファイル名を指定しても親ディレクトリを選ぶだけで、そのファイルは作成しません。--results-dir を推奨します。リポジトリルートでは既定は results/ です。 | `--output results/legacy.json` |
| `--model MODEL` | ABB の置換先モデルを上書きします。既定は選択したサービスの設定です。ネイティブ ACP のモデルは Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | ストリーミング時の旧メモリ一時保存しきい値です。単位はバイト、既定は 262144（256 KiB）。保存内容を切り詰めません。 | `--llm-trace-max-bytes 262144` |

### 使用例

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
agentbench certify AGENT_ID --sdk local --yes --no-view --results-dir results/certification
```

## `observe`

一つのネイティブ入力を実行し、出力とトレースを保存します。SDK の Case 生成と Judge は使いません。現在は Docker の oneshot 実行が必要です。--list と --show は読み取りのみです。

```text
agentbench observe [AGENT] [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `AGENT` | 有効な Agent の ID または一覧番号です。省略時は対話選択。--agent とは併用できません。 | `react-agent` |
| `--agent AGENT` | 位置引数の代わりに Agent ID または番号を指定します。両方は指定できません。 | `--agent react-agent` |
| `--registry PATH` | Agent 登録表を指定します。既定はプロジェクトの resources/registry.toml です。 | `--registry resources/registry.toml` |
| `--list` | 有効な Agents を一覧表示し、実行せず終了します。既定は無効です。 | `--list` |
| `--input PATH` | UTF-8 JSON から一つのネイティブ入力を読み込みます。テキストは引用符付き JSON 文字列にします。省略時は observe フィールドまたは JSON を対話入力します。 | `--input native-input.json` |
| `--output DIR` | Observe 成果物のルートです。実行 ID ごとのサブディレクトリを作ります。既定は results/observe です。 | `--output results/observe` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--model MODEL` | ABB の置換先モデルを上書きします。既定は選択したサービスの設定です。ネイティブ ACP のモデルは Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--timeout SECONDS` | Agent 実行のタイムアウトを有限の正数の秒で上書きします。既定は Agent の実行設定です。 | `--timeout 300` |
| `--show DIR` | 保存済み observe 実行をオフライン表示して終了します。Agent は実行せず、他の実行オプションは使いません。 | `--show results/observe/RUN_ID` |

### 使用例

```bash
agentbench observe --list
agentbench observe react-agent --input native-input.json --output results/observe --timeout 300
agentbench observe --show results/observe/RUN_ID
```

## `view`

保存済み結果をローカル Web ビューアーで表示します。先に Web をビルドし、表示された View URL 全体を開いてコマンドを動かし続けます。Ctrl+C で停止します。

```text
agentbench view RESULT_LOG [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `RESULT_LOG` | 既存の JSON 結果ファイルを指定します。通常は Result saved の events.json。ディレクトリではなくファイルを渡します。 | `results/suites/SUITE_ID/events.json` |
| `--host ADDRESS` | ビューアーの待受アドレスです。既定は 127.0.0.1。 | `--host 127.0.0.1` |
| `--port N` | 待受ポートです。0～65535、既定は 8765。0 は自動割り当て、既定ポート使用中は別の空きポートを選べます。 | `--port 0` |

### 使用例

```bash
agentbench view results/suites/SUITE_ID/events.json
agentbench view results/suites/SUITE_ID/events.json --host 127.0.0.1 --port 0
```

## `sdk list`

SDK ディレクトリから発見したプラグイン名を一覧表示します。全実行依存関係のインストールを確認するものではありません。

```text
agentbench sdk list [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |

### 使用例

```bash
agentbench sdk list
```

## `sdk show`

SDK プラグインを読み込み、保存元・実行方式・暗黙選択の可否を表示します。

```text
agentbench sdk show NAME [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `NAME` | SDK ディレクトリ名を指定します。大文字・小文字を区別しません。sdk list の名前を使います。 | `kuma` |

### 使用例

```bash
agentbench sdk show kuma
agentbench sdk show local
```

## `resume`

保存済み Cases・設定と現在の認証情報を使い、Suite の復旧可能な未完了作業を再開します。新しい Cases は生成せず、完了済みを意図的に再実行しません。

```text
agentbench resume SUITE [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `SUITE` | 保存済み Suite の ID・ディレクトリ・events.json パスを指定します。ID は --suite-root 内で解決します。 | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Suite ID ディレクトリを含む親ディレクトリです。既定は作業ディレクトリの results/suites。 | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |

### 使用例

```bash
agentbench resume results/suites/SUITE_ID
agentbench resume SUITE_ID --suite-root results/my-run/suites --env-file .env.testing
```

## `retry`

元 Suite の未完了 Case 一つを元入力で復旧します。保存状態によりリクエストを再開するか、最初の入力から再実行します。再実行条件は引き続き適用されます。

```text
agentbench retry SUITE --agent ID --case N [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `SUITE` | 保存済み Suite の ID・ディレクトリ・events.json パスを指定します。ID は --suite-root 内で解決します。 | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Suite ID ディレクトリを含む親ディレクトリです。既定は作業ディレクトリの results/suites。 | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--agent ID` | 元 Suite の正確な Agent ID を指定します。一覧番号ではありません。 | `--agent react-agent` |
| `--case N` | Case 番号を指定します。1 から始まる正の整数で、--agent の Case を対象にします。 | `--case 1` |

### 使用例

```bash
agentbench retry results/suites/SUITE_ID --agent react-agent --case 1
```

## `reuse`

保存した Case 入力で新しい Agent 実行・証拠収集・Judge 判定を行い、関連する再実行 Suite に保存します。元結果を維持し、新入力は生成しません。完了 Case の再実行に使います。

```text
agentbench reuse SOURCE [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `SOURCE` | 保存済み Suite ID/パス、Case ID、artifact run ID、case.json、試行パスを指定します。Suite は既定で全 Cases を選び、--agent と --case で一つに絞れます。曖昧な ID は保存元を明示します。 | `CASE_ID` |
| `--suite-root DIR` | 保存済み Suite の検索先をこのディレクトリに限定します。既定はプロジェクトの results と登録済み外部 Suites です。 | `--suite-root results/my-run/suites` |
| `--agent ID` | Suite を保存元とするときに正確な Agent ID を指定します。--case と併用し、両方省略すると全 Cases を再実行します。 | `--agent react-agent` |
| `--case N` | Suite 内の Case 番号です。1 から始まる正の整数で、--agent と併用します。直接の Case ID とは併用しません。 | `--case 2` |
| `--output-root DIR` | 再実行 Suites の親ディレクトリです。新しい Suite は DIR/SUITE_ID に保存します。既定は元 Suite の親です。この直下の互換性がある実行中 Suite にのみ参加します。 | `--output-root results/reruns` |
| `--env-file PATH` | 環境ファイルを指定します。既定はプロジェクトの .env で、シェルの環境変数が優先されます。 | `--env-file .env.testing` |
| `--model MODEL` | 新しい評価の置換先モデルです。既定は保存済みモデル設定で、ネイティブ ACP は Agent の設定に従います。 | `--model openai/gpt-4.1-mini` |
| `--max-steps N` | 新しい評価の SDK 対話ステップ予算で、正の整数です。既定は保存済み実行設定。保存 Case に新しい入力を生成しません。 | `--max-steps 3` |

互換性のあるリクエストは実行中の再実行 Suite に参加できます。意図的なリクエストごとに新しい実行を追加します。--no-view、--yes、--sdk、--cases はなく、結果/ビューアーのリンクを表示します。

### 使用例

```bash
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent react-agent --case 2
agentbench reuse results/suites/SUITE_ID --output-root results/reruns --max-steps 3
```

## `clean`

プロジェクト results の未参照のトップレベル履歴を cache/history-trash に移し、保存 Suites と参照成果物を維持します。先に確認し、実際の整理前に実行とビューアーを停止します。

```text
agentbench clean [OPTIONS]
```

| 引数 | 目的と既定の動作 | 使用例 |
| --- | --- | --- |
| `-h, --help` | このコマンドのヘルプを表示して終了します。 | `--help` |
| `--dry-run` | アーカイブ対象を表示し、ファイルを移動しません。既定は無効です。 | `--dry-run` |
| `-y, --yes` | アーカイブ確認を省略します。既定では確認します。実際の整理前に実行とビューアーを停止します。 | `--yes` |

### 使用例

```bash
agentbench clean --dry-run
agentbench clean
```

## 使用例で使うファイル

対応する引数を使う前にファイルを作成します。JSON は正しい形式で、sdk-options.json はオブジェクトが必要です。以下の SDK オプションは kuma/local 用で、他のプラグインは異なるキーを使えます。

`sdk-options.json`:

```json
{
  "timeout": 2400,
  "max_steps": 3
}
```

`build-settings.toml`:

```toml
[build]
model = "openai/gpt-4.1-mini"
timeout_seconds = 120
```

`native-input.json`:

```json
"Describe your capabilities and limitations."
```

native-input.json は Agent のネイティブ入力形式に合わせます。answers.txt は計画の質問への実際の回答です。adapter-context.json は -b のデプロイコンテキストで、フィールドは Agent ごとに異なり、汎用のコピー用オブジェクトはありません。

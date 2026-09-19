# Agent の追加

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | 日本語 | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

**環境 → ソースのインポート → 設定 → 静的確認 → local スモークテスト → KUMA → view →
引き渡しまたは認証** の順に進めます。コマンドはこの ABB checkout のルートで、その仮想環境を
有効にして実行してください。`SOURCE`、`AGENT_ID`、`NN-name`、結果パスは実際の出力に置き換えます。

Coding agent は最初に `AGENTS.md`、追加依頼の issue、上流のセットアップ手順を読みます。
作業範囲、現在の checkout、`git status` を記録し、無関係な変更を保護してください。
README の記載だけで実行可能と判断してはいけません。

**停止する条件：**段階ごとの承認を求められた場合は、各段階のコマンド、結果、証拠パス、
次の作業を報告して承認を待ちます。それ以外は、承認済みの範囲を毎回聞き直さず進めます。
新たな有料・外部処理の前には、モデル呼び出しと、ソースの文脈・profile・評価証拠の送信が
承認に含まれることを確認します。既存の承認は有効です。認証情報や必須判断が不足する場合、
未対応のデプロイ、原因未解決の失敗では、それに依存する作業を止め、完了分を保存します。
キーや `.env` の内容は表示しません。チェックポイントは証拠の確認であり、毎回の許可要求ではありません。

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
python -m agentbench --help
python -m agentbench sdk list
docker info
```

sdk list に kuma が表示され、ABB と同じユーザーで docker info が成功することを確認します。
ダウンロードと設定生成だけなら Docker は不要ですが、-c の認証には必要です。
ホストと評価コンテナの SDK インストールは別です。

有料サービス設定前に harness を確認します。

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

期待値は `Case execution: 1/1 completed | Judge: pass=1` です。正確な
`OFFLINE_RESULT=` パスを保存してください。この決定的 echo demo は Docker、キー、モデル不要で、
対象 Agent の試験ではありません。失敗したら先にホスト環境を直します。チェックポイントでは
checkout パス/revision、CLI/SDK 検出、demo 結果を報告します。SDK 検出は統合対応の
証明ではありません（第 2 節）。

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

## 2. ソースをインポートしてから設定を生成する

モデル呼び出し前に確認できるよう、まずインポートだけ実行します。

```bash
python -m agentbench agent add https://github.com/owner/repository
```

`SOURCE` は HTTPS リポジトリ本体の URL で、ファイルや `/tree/branch` URL ではありません。
`/absolute/path/to/local-agent` や PowerShell の `C:\work\local-agent` のようなローカル絶対
ディレクトリも指定でき、`-d` は不要です。GitHub はデフォルトブランチの revision を使い、
`--revision` はありません。ローカルは `.git` を除き SHA-256 を記録します。同じ正規化済み
ソースへの再実行は既存 unit を再利用し、変更されたローカルソースを再コピーしません。

**確認 — インポート完了：**実際の unit パスと `source-manifest.json` の revision を記録します。
元の入口、prompt、ツール、入力/状態スキーマ、UI の呼び出し、Python 制約、lockfile を読み、
外部サービスと公開するインターフェースを特定します。テキスト graph は PDF アップロード UI
とは別です。インポートだけでは実行可能 Agent として登録されません。`agent add` を飛ばして
代替実装をレジストリーへ直接追加しないでください。

デプロイ内容を明確にしたら、同じソースで生成します。

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view
```

`-b` は計画・生成・検証・`adapting` 登録を行い、**Docker ビルドは行いません**。
KUMA は計画前に最新カタログを取得します。目的、可用性、正確なバージョン、証拠要件を確認し、
そのスナップショットを保存します。他の Agent の戦略 ID をコピーしないでください。
取得失敗時は認証情報や接続を修正するまで停止し、選択を捏造しません。

計画が情報を要求したら、事実に基づく回答をローカル UTF-8 ファイルに保存して再開します。

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view --answers answers.txt
```

テキストと原生入力の対応、セッション寿命、除外する UI、サービスと依存関係を説明し、業務入力を
作り上げないでください。再試行前に `build-result.json` と失敗した `steps/` を確認します。
完了ファイルは保持・再検証され、手動編集との競合は生成を停止します。全進捗を削除したり、
原因を変えずに有料リクエストを繰り返したりしないでください。

**この revision の制限：**`local` SDK は評価を提供しますが、統合要件/検証 hook がありません。
`add -b --sdk local` は `Selected SDK has no onboarding requirements and validation` で停止します。
ここでは KUMA で生成後、第 5 節の local 評価を使います。KUMA 認証情報がなければ自動生成を
停止します。local の生成対応は別のコード変更であり、別 checkout の修正が存在するとは限りません。

以下の一括コマンドは、デプロイを理解し、中間承認なしの生成・認証が承認済みの場合だけ使用します。

```bash
python -m agentbench agent add https://github.com/owner/repository -b -c --sdk kuma --no-view
```

`-c` はビルドと認証実行であり、有料呼び出しが発生し得ます。静的確認ではありません。
手動設定にも使えます。現在の自動生成は LangGraph 対応で、未対応 framework を LangGraph と偽らないでください。

| オプション | 用途 |
| --- | --- |
| `--sdk kuma` / `--sdk local` | 明示的に選択。検出できることと生成対応は別です。 |
| `--no-view` | viewer を起動せず結果を保存。 |
| `--build-model MODEL` | 厳密な構造化出力を備えた設定生成モデル。 |
| `--model MODEL` | 認証時の Agent モデル。 |
| `--answers answers.txt` | 前の計画への回答。 |
| `--with-observe` | `-b` と併用し observe 入力案内を生成。 |
| `--build-settings settings.toml` | `[build]` テーブルによる上書き。 |
| `-y` | 実行が承認済みの場合だけ CLI 確認を省略。 |

生成モデルの優先順位は `--build-model`、settings `model`、`OPENROUTER_BUILD_MODEL`、
`OPENROUTER_MODEL` です。予算や再試行の変更前に
[同梱設定（英語）](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)を確認してください。

## 3. 各ファイルの役割を理解する

Agent 単位のディレクトリは `resources/agents/NN-name/` です。取得したソースの周囲に
接続ファイルが生成されるので、実行前に全部を手書きする必要はありません。

```text
resources/agents/NN-name/
├── agent/                   # インポートした上流またはローカルのソーススナップショット
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

## 4. 実行前のレビューと静的検証

**確認 — 設定完了：**成功メッセージだけでなく全生成ファイルを確認します。出典と次の境界を調べます。

- descriptor が元の graph を指すこと。上流に `langgraph.json` がない場合は
  `abb-langgraph.json` など最小 descriptor の追加を出典に明記し、graph 自体を改変しません。
- binding は同期・引数なし factory から本物の Agent を呼び、`config`/callbacks、例外、
  raw output を保持します。UI のメッセージ追加/active-agent の寿命を再現し、Case を隔離、
  close で清掃します。グローバル可変会話状態や例外の隠蔽は不可です。
- 出力フィールドは本当の返信を抽出し、証拠には完全な状態を残します。テキストから提供できない
  複数の必須業務フィールドがある場合は停止します。
- 上流 lockfile を互換 Python でインストールし、ホスト ABB 依存と分離します。uv の project、
  lockfile、実行 Python を一致させ、独立 `/opt/venv` で読み取り専用ソースへのインストールを
  避けます。実行 Python の pip も確認します。
- 追加ルートや binding/runtime の COPY を含む **SDK overlay 適用後**の設定を確認します。
  外側 TOML の検証だけでは不十分です。
- profile は実在するツール、利用者が渡すデータ、できない操作を記します。現在の KUMA 生成は
  `input_type: text`、正確な英語の三見出し、カタログからの戦略選択が必要です。
  未実装のブラウズ、アップロード、コード実行、永続化を能力として宣言しません。

手動修正後、統合で使う静的 validator を実行します。

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
unit = Path("resources/agents/NN-name")
print(validate_unit(unit, plugin))
PY
```

ファイルとインストール済み SDK parser をオフライン確認します。Agent は実行せず、カタログ
context を渡さなければ最新カタログ取得/選択検証もしません。生成は取得したスナップショットを
使い、KUMA 実行前にもサービス規則を確認します。静的成功は実行成功ではありません。
複雑な binding は実 adapter 境界、Case 隔離、config 伝達、対応する場合の async、例外を
オフライン試験します。fixture は自己完結させ、任意 unit がない場合は明示的 skip にします。

## 5. local スモーク Case を一つ実行する

設定済みのテキスト Agent を小さく試します。

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

実 Docker Agent とモデル interception を使い、固定テキスト Case と local Judge で評価します。
Docker とモデル設定が必要で、モデル料金は発生し得ます。KUMA のキー/クレジットは不要ですが、
認証情報なしのオフライン echo demo とは違います。固定 Case は profile から生成されず、
記事処理や専門家 handoff を網羅するとは限りません。

**確認 — local：**Suite パス、詳細ディレクトリ、返信、trace 状態、Judge を保存します。
実行成功と host acceptance を確認して初めて実行可能と報告します。最初の実行後は失敗時も
view を確認します（第 7 節）。import や fixture 試験だけでは代替できません。

汎用 Case に必要な文脈がない場合は、承認の範囲で source に基づく入力と `observe` を使えます。
テキスト binding の `native-input.json` は JSON 文字列、他の場合は実際の schema に合わせます。
「与えられた文章を読め」とだけ書かず、実際の本文や業務データを渡してください。

```bash
python -m agentbench observe AGENT_ID --input native-input.json
```

observe は KUMA Case/Judge なしで原生実行を記録しますが、モデル/ツール料金は発生し得ます。
個別観察で失敗 benchmark を成功扱いにはできません。直接 KUMA を依頼された場合は静的確認後に
第 6 節へ進み、local を省略したなら未実施と報告します。

## 6. 新しい KUMA 評価を実行する

配置済み profile と現在の戦略を確認し、KUMA/モデル利用と証拠送信の承認を確認して一件実行します。

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

local 成功は KUMA 互換性の証明ではありません。profile の変更は将来の Case のみに影響します。
生成 Case が必要データを渡し、実装済み操作を求めているか確認してください。Case の欠陥と
Agent の問題を併記し、合格のために元の入力、出力、Judge 証拠を編集しないでください。

同じ実行の生成、Agent 呼び出し、提出、Judge polling を追跡します。非同期受付は判定ではなく、
待機中に重複評価を開始しません。timeout/エラーは保存された完了/復旧状態を確認してから
再開や再試行を判断します。再実行安全性とツール副作用を尊重し、安全フラグを書き換えて強制
復旧しません。新しい `evaluate` は新 Suite と通常は新 Case を作り、旧 Case の対照再試験ではありません。

## 7. view を開き、結果を分けて判断する

最初の local 後、KUMA 後、失敗診断・再試行・完了報告前に viewer を開きます。
headless なら同じ JSON/trace を読み、UI レビュー未実施と明記します。

```bash
python -m agentbench view results/suites/ACTUAL_SUITE_ID/events.json
```

実際の `Result saved` / `Open later` パスを使います。オフライン demo は時刻付き
`OFFLINE_RESULT` を出力します。推測した名前や古い Suite を使わないでください。
パスを含む完全な `View:` URL を開き、サーバーを動かしたままにします。終了は Ctrl+C です。
`--no-view` でも結果は保存されています。

**Suite → Case → 各入力/返信 → モデル/ツール/handoff trace → Judge と証拠 →
実行/清掃/host acceptance** の順で確認します。handoff 成功は専門家の作業完了ではなく、
書き込みの主張だけでは実際の書き込みを証明できません。

| 証拠 | 解釈と次の行動 |
| --- | --- |
| 実行成功 + host accepted + Judge pass | この Case は成功。範囲を記録し、全能力に一般化しない。 |
| 実行成功 + host accepted + Judge issue | 統合は実行できた。行動上の問題を保存し、合格目的で prompt を変えない。 |
| 原生例外 / execution failed | Judge があっても成功実行ではない。昇格前に診断する。 |
| 部分 trace / insufficient evidence / host rejected | 証拠不足を分けて報告。OTel complete は全ツール内容の記録を意味しない。 |
| 記事/データ欠落、実行不能な Case 操作 | Case/profile 制限を記録し、根拠のある Agent 主張を別途判断。データを捏造しない。 |

`results/observe/<run-id>/` の `run.json`、`evaluation/case.json`、`evaluation/inputs/`、
`evaluation/manifest.json`、`evaluation/judge/report.json` を存在する範囲で確認します。
欠落は段階未完了を示し得ます。判定を仮定しないでください。非ゼロ終了は Judge issue の場合も
あり、必ずしも crash ではありません。JSON export 単体は完全 trace の独立アーカイブではありません。

## 8. 認証が必要か判断する

`evaluate` は registry 昇格や Case 数変更をしません。`run` の選択対象にする必要があるなら、
registry の件数と追加実行の承認を確認して実行します。

```bash
python -m agentbench certify AGENT_ID --sdk kuma --no-view
```

certify は設定件数を再実行し、過去の証拠を承認するだけではありません。全 Case が呼び出し
エラーなしで完了すれば、Judge の問題があっても `adapting` から `ready` へ昇格できます。
ready 済みなら再実行せず戻るため、変更後は evaluate を使います。実行の阻害を隠す手動 ready
変更は不可です。利用者が評価成功で追加完了と認めたら実際の registry 状態を報告して停止し、
ラベルだけのために追加の有料認証をしないでください。

## 9. 失敗した境界を診断する

最初の失敗と保存証拠から始め、可能なら最小オフライン再現を作ります。graph/binding、単一/複数
tool call、sync/async、固定依存/ホスト環境など一度に一要因だけ比較します。診断 script は
配布 unit 外へ置きます。デプロイ修正と上流行動変更は分け、後者は別提案にします。
interception 無効化、エラー隠蔽、成功したツール結果の捏造は禁止です。

| 症状 | 確認・対処・停止条件 |
| --- | --- |
| agentbench 不在、別 checkout の import | 現在の venv と `python -m agentbench` を使い、Agent 修正前に editable install を確認。 |
| Docker 不可、権限、image architecture | 同一ユーザーの `docker info` と platform を確認。必要な権限を得て隔離は維持。 |
| SDK 検出済みだが onboarding hook 不在、kuma import 失敗 | 検出は能力/依存検証ではない。生成対応 SDK と固定 requirements を使用。 |
| catalog/auth/network | キーの有無、shell 優先順位、endpoint、接続を秘密を表示せず確認。解消まで生成停止。 |
| 構造化出力拒否、needs_input、競合 | plan/step 記録を読み、適合モデル、事実の回答、確認済みファイル修正を行い、該当段階だけ再試行。 |
| uv project/lock 不一致、pip 不在、container import | Python 範囲、lock 場所、interpreter、依存隔離、COPY を確認。静的成功はインストール証明ではない。 |
| 外側 TOML は正常だが overlay 失敗 | 空の `tool_routes = []` と追加 `[[llm_interception.tool_routes]]` の競合を確認し、不要な空宣言だけ除く。必須ルートと interception は保持。 |
| 複数 handoff で INVALID_CHAT_HISTORY | AI tool-call ID と ToolMessage を照合し原 graph をオフライン再現。単一成功は並行成功を保証しない。 |
| Judge が復旧不在や外部操作の主張を指摘 | モデルが先の例外を受け取ったか、対応ツールが存在/実行されたかを確認。文章、状態、証拠の限界を分離。 |
| viewer 空白、不達、古い結果 | web/dist を構築し、正確な URL/ファイル、サーバー継続、ポート権限を確認。viewer 修復のために有料評価を繰り返さない。 |

Article Explainer では local 対話は動き、一度の KUMA は原生の並行 handoff で失敗、別の
実行は完了したものの行動上の問題が見つかりました。Case の記事本文も欠落していました。
これは診断例であり、他 revision/モデル/Case の結果を保証しません。戦略 ID も再確認なく流用しません。

## 10. 引き渡しチェックリストと完了報告

ソース/revision、unit パス、生成/手動修正ファイル、コマンド、実結果/view パス、local/KUMA
の実行・host acceptance・Judge を別々に報告します。未試験の能力、既知の失敗、registry と
Git 状態（ローカルのみ、commit/push/PR）も記します。コード/docs と `.venv`、秘密、image、
cache、lock、結果を区別し、秘密を commit しません。

合意した追加目標に証拠が揃えば停止します。行動上の問題は有効な benchmark 結果であり、
必ずしも追加作業の未完了ではありません。偶然の合格まで回したり、対象 Agent を黙って直したり
しません。commit/PR が依頼されたら、別の承認済み段階としてレビュー可能な差分を用意します。

参照：[障害対応（英語）](../Troubleshooting.md)、[既知の問題（英語）](../Documentation-Issue-Audit.md)、
[生成実装（英語）](../../agentbench/onboarding/build_agent_env/README.md)。

# `registry.toml` の読み方

[English](../Registry.md) | [中文](Registry.zh-CN.md) | [Français](Registry.fr.md) | 日本語 | [한국어](Registry.ko.md)

[README に戻る](README.ja.md) · [ABB の起動方法 — 英語](../Guide.md)

[Agent 登録表](../../resources/registry.toml) は、ABB が利用できる対象 Agents、ローカルの
接続用ディレクトリ、既定の評価予算を記録します。`agentbench run` は、
`enabled = true` と `status = "ready"` の両方を満たすエントリを選択します。

## エントリを読む

ファイルの先頭で形式のバージョンを指定し、各 `[[agents]]` ブロックで Agent を登録します。

```toml
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "folder-mover-agent"
path = "resources/agents/01-folder-mover-agent"
enabled = false
status = "ready"
framework = "langgraph"
source = "C:\\Song_startup\\benchmark\\04-folder-mover-agent\\folder-mover-agent"
case = 1
step = 3
```

この例は LangGraph Agent を登録し、既定で独立した Case を一つ、各 Case につき最大三回の
対話ステップを設定しています。`ready` ですが無効になっているため、`run` の対象には
入りません。`source` のパスは、あるマシンでの元のインポート先を示す例です。
利用者が同じディレクトリを作る必要はありません。

| フィールド | 意味 |
| --- | --- |
| `schema_version` | ファイル全体の形式識別子。`"defuzex-bench.registry.v1"` を Agent ブロックの前に一度だけ記載します。 |
| `[[agents]]` | TOML のテーブル配列構文。各ブロックは別の Agent 登録を表します。 |
| `agent_id` | CLI で使う一意の識別子。その Agent の `agent.toml` の `agent_id` と一致する必要があります。 |
| `path` | ローカルの接続用ディレクトリ。登録表が標準の場所にある場合、リポジトリのルートからの相対パスとして解決されます。内部のソース用 `agent/` ではなく、`agent.toml` と `requirement.md` を含む外側のディレクトリを指します。リポジトリ内に置く必要があります。 |
| `enabled` | Agent を選択できるかどうか。`false` は `run` と単体評価の `evaluate` から除外します。TOML の真偽値を使い、省略時は `true` です。 |
| `status` | 接続作業の状態。`adapting` は認証待ち、`ready` は有効であれば既定の `run` に参加できることを示します。省略時は `unknown` となり、`run` から除外されます。 |
| `framework` | `langgraph` や `acp` などのフレームワーク名。マニフェストと実際の接続方法に合わせます。実行時の Adapter と起動設定は `agent.toml` で定義します。 |
| `source` | リポジトリ URL やローカルのインポート元など、元のソースの所在。変更してもインポート済みコードの置換や起動設定の変更は行われません。省略時は空文字列です。 |
| `case` | この Agent に実行する独立した Cases の数。正の整数が必要で、省略時は `1` です。 |
| `step` | SDK に渡す Case ごとの対話ステップ数の上限。指定する場合は正の整数が必要です。省略時は SDK の既定値を使います。実際のステップ数はこれより少ない場合があります。 |

`agent_id`、`path`、`framework` は必須の空でない文字列です。TOML の二重引用符付き
文字列では、Windows パスのバックスラッシュを `\\` と記述します。

## `case` と `step` の違い

- `case = 1`、`step = 3`：独立した Case 一つに、最大三回の順序付き入力。
- `case = 5`、`step = 3`：独立した Cases 五つに、それぞれ最大三回の入力。
- 一つの対話ステップは対象 Agent に一つの入力を渡します。その処理中には複数のモデル
  呼び出しやツール呼び出しが発生し得ます。`step` はツール呼び出し数や内部の推論反復数
  の上限ではありません。また、どちらのフィールドも並列実行数を設定しません。

複数の対話ステップに対応していない Agent もあるため、Benchmark が各 Agent に設定した
既定の `step` 値を維持することを推奨します。

選択した SDK は生成と実行の際にステップ予算を使います。明示的な SDK オプション
`max_steps` は登録表の `step` より優先されます。`evaluate` の `--cases` は `case` を、
`--max-steps` はステップ予算を、その実行に限って上書きします。登録表は変更しません。

```bash
agentbench evaluate react-agent --cases 2 --max-steps 3 --no-view
```

## Agent の選択と既定値の変更

例の Agent を `run` に含めるには `enabled = true` にします。新規接続の `adapting` Agent
では、[接続設定](How%20To%20Add%20Agent.ja.md)を完了し、有効な状態で認証します。

```bash
agentbench certify folder-mover-agent --no-view
```

認証に成功すると `ready` になります。この状態は接続の準備完了を示し、Judge が振る舞い
上の欠陥を発見しないことを保証しません。状態を手動で変更しても認証は実行されません。
`run` と異なり、`evaluate` は `ready` で絞り込まず、有効な Agent を選択できます。

```bash
agentbench observe --list
agentbench run --no-view
```

`case` と `step` の変更は今後の実行の既定予算に反映されます。保存済みの Cases と結果は
記録された設定を維持します。`run` は選択前に全エントリを検証するため、無効な Agent
でも接続用ファイルが不足すると登録表を読み込めない場合があります。パスの有効性、
識別子の一意性、必須ファイルを維持してください。[登録済み Agents](Agents.ja.md)も
参照してください。

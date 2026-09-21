# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench — Agent の振る舞いを評価"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  日本語 |
  <a href="README.zh-CN.md">中文</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 以降" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## ABB とは？

AgentBehaviorBench は AI Agent のための振る舞いテストシステムです。具体的なタスクで
Agent が受け取った指示、呼び出したモデルやツール、発生させた変更、そして収集された
証拠が最終回答を裏付けているかを評価します。

ABB は最終テキストだけを比較するものではありません。Case では、安全境界、指示の処理、
ツールの利用、状態の変更、Agent が自身の操作を正確に報告したかなどを検証できます。
各評価では Case、Agent の出力、実行証拠、Judge の結果を保存します。

## 概要

ABB は異なるフレームワークで実装された多数の Agent を登録し、同じ評価パイプラインで
実行できます。評価 SDK は各 Agent が宣言した能力に基づいて Cases を生成します。ABB は
各 Case を隔離環境で実行し、モデル呼び出し、ツール呼び出し、ファイルへの影響、Agent の
出力を収集した後、SDK がその証拠を使って観察された振る舞いを判定します。

![AgentBehaviorBench アーキテクチャ](../figures/abb-architecture-v2.png)

Agent Registry は、テスト対象のソースリビジョンと ABB が Agent を起動する方法を記録します。
Harness は Cases をスケジュールし、コンテナを起動し、Agent Run を実行し、宣言された通信を
ルーティングして trace とファイルシステム証拠を収集します。実行状態と Judge の判定は別です。
Agent が正常に実行されても、Judge が振る舞い上の問題を検出する場合があります。

## 現在インポート済みの Agents

以下の Agent ソースが現在 ABB に登録されています。

ABB は現在、LangGraph Agent のネイティブ統合と、Agent Client Protocol（ACP）を介して
公開される Agent をサポートしています。

各 GitHub revision リンクは `agent.toml` で固定された正確な commit を指します。
Folder Mover Agent はローカルディレクトリからインポートされているため、ABB は Git commit
ではなくソース内容のダイジェストを記録します。

| Agent | GitHub ソース | 選択されたリビジョン |
| --- | --- | --- |
| `folder-mover-agent` | ローカルソース | `sha256:2826f61…` |
| `company-research-agent` | [guy-hartstein/company-research-agent](https://github.com/guy-hartstein/company-research-agent) | [`c714203`](https://github.com/guy-hartstein/company-research-agent/commit/c7142035a1cd413e34ad0595dbe9b5ca8b0308e8) |
| `react-agent` | [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) | [`9bbd82d`](https://github.com/langchain-ai/react-agent/commit/9bbd82d84905acc37f527b1f372dae841016f3b4) |
| `ai-hedge-fund-crypto` | [51bitquant/ai-hedge-fund-crypto](https://github.com/51bitquant/ai-hedge-fund-crypto) | [`c6750e0`](https://github.com/51bitquant/ai-hedge-fund-crypto/commit/c6750e0041cb2e528856864783585427c45cc34d) |
| `labscript-ai` | [KRATSZ/LabScript-AI](https://github.com/KRATSZ/LabScript-AI) | [`abff772`](https://github.com/KRATSZ/LabScript-AI/commit/abff77285eacc98f245a27059d7d2c34969dcc2c) |
| `multi-agent-cad` | [Pan-Chera/Multi-Agent-CAD](https://github.com/Pan-Chera/Multi-Agent-CAD) | [`f31a2f6`](https://github.com/Pan-Chera/Multi-Agent-CAD/commit/f31a2f65aa1b1e16fa6c45f1d642142fb696db28) |
| `autoresearch-agents` | [hwchase17/autoresearch-agents](https://github.com/hwchase17/autoresearch-agents) | [`552fd6a`](https://github.com/hwchase17/autoresearch-agents/commit/552fd6a1bd607f6645cd4baba0a98858d62e8815) |
| `langchain-streamlit-template` | [hwchase17/langchain-streamlit-template](https://github.com/hwchase17/langchain-streamlit-template) | [`3c676a6`](https://github.com/hwchase17/langchain-streamlit-template/commit/3c676a670d1f69bcc4c76b692126db1922101d5f) |
| `curiosity` | [jank/curiosity](https://github.com/jank/curiosity) | [`41c9195`](https://github.com/jank/curiosity/commit/41c91954788f04b15332d2b86e265c5433fa4813) |
| `readwren` | [muratcankoylan/readwren](https://github.com/muratcankoylan/readwren) | [`3d0bfe4`](https://github.com/muratcankoylan/readwren/commit/3d0bfe481a340f247c749c082b7a65c877c12de1) |
| `tablegpt-agent` | [tablegpt/tablegpt-agent](https://github.com/tablegpt/tablegpt-agent) | [`26bc576`](https://github.com/tablegpt/tablegpt-agent/commit/26bc576bb21fc1c296d829e863c97290e92bfd8e) |
| `minimax-code` | [MiniMax-AI/minimax-code](https://github.com/MiniMax-AI/minimax-code) | [`a5639bc`](https://github.com/MiniMax-AI/minimax-code/commit/a5639bcc6146754e01f1ae18bb88545f18299fd6) |
| `claude-agent-acp` | [agentclientprotocol/claude-agent-acp](https://github.com/agentclientprotocol/claude-agent-acp) | [`d421f56`](https://github.com/agentclientprotocol/claude-agent-acp/commit/d421f56a6c43cde16d9a7531d08a750a5ef2f04a) |
| `qwen-code` | [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) | [`1026c4a`](https://github.com/QwenLM/qwen-code/commit/1026c4a50f4a32f77da98bdacfba2e5faa8cc70a) |
| `opencode` | [anomalyco/opencode](https://github.com/anomalyco/opencode) | [`014614d`](https://github.com/anomalyco/opencode/commit/014614d35b397775e5d397a490fc72368c894ec2) |
| `kilo-code` | [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode) | [`01ef456`](https://github.com/Kilo-Org/kilocode/commit/01ef456fe7f41aa1f7b8a4e6b545dd1e0fbeeceb) |
| `goose` | [aaif-goose/goose](https://github.com/aaif-goose/goose) | [`1a4249a`](https://github.com/aaif-goose/goose/commit/1a4249ac9f23c6e6e2526d4b54dbbf3bb09ba204) |
| `cline` | [cline/cline](https://github.com/cline/cline) | [`d718dd1`](https://github.com/cline/cline/commit/d718dd16f850c4c915a8214441a831e00cb28c75) |
| `kimi-cli` | [MoonshotAI/kimi-cli](https://github.com/MoonshotAI/kimi-cli) | [`86f1364`](https://github.com/MoonshotAI/kimi-cli/commit/86f136422a0aae6b217ea49e7ea1d2e8a1defcd2) |
| `pi-coding-agent` | [earendil-works/pi](https://github.com/earendil-works/pi) | [`13cbf77`](https://github.com/earendil-works/pi/commit/13cbf77df2396303013a41646bcfa77b4271ae56) |
| `copilot-cli` | [github/copilot-cli](https://github.com/github/copilot-cli) | [`ab6139c`](https://github.com/github/copilot-cli/commit/ab6139c694ba09ab4e8ac76b6046daa6b5d89616) |
| `openclaw` | [openclaw/openclaw](https://github.com/openclaw/openclaw) | [`ec9c1a1`](https://github.com/openclaw/openclaw/commit/ec9c1a13db8938e5a3eaa51fca2e981cde2395a9) |
| `hermes-agent` | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | [`345cd2b`](https://github.com/NousResearch/hermes-agent/commit/345cd2b057a452236de401d3534b8502a7465e8d) |
| `openhands` | [OpenHands/OpenHands-CLI](https://github.com/OpenHands/OpenHands-CLI) | [`2963442`](https://github.com/OpenHands/OpenHands-CLI/commit/2963442dacc7cea44e39b7c4e73724295c853465) |
| `deepagents-code` | [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) | [`a764619`](https://github.com/langchain-ai/deepagents/commit/a764619aa8c850bc75e2e916cf53a587637d8c81) |

`resources/registry.toml` が、Agent の有効状態、準備状態、Case 数、step 上限の正式な情報源です。

## 評価 SDK と Judge

正式な評価では現在 [KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX)
を使用し、`kuma-defuzex[otel]==0.3.1` に固定しています。KUMA は振る舞いテストの Cases を
生成し、ABB が収集した証拠を受け取り、DefuzeX Judge に送信します。判定結果と評価内容は
Suite artifacts とともに保存されます。

ABB には、決定論的なオフライン開発とテスト用の `local` SDK plugin も含まれます。
これは正式な benchmark 結果に使用される Judge ではありません。

## ABB CLI ヘルプ

```text
usage: agentbench [-h]
                  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
                  ...

登録済み Benchmark Agents の実行、認定、確認を行います。

位置引数：
  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
    run                 有効かつ ready のすべての Agents を実行します。
    agent               Agent ソースをインポートして確認します。
    view                保存済み結果をローカルビューアで開きます。
    certify             adapting Agent を実行し、成功後に ready へ昇格します。
    observe             有効な Agent を実行し、trace を保存します。
    evaluate            独立した SDK Cases で Agent を評価します。
    clean               参照されていないローカル履歴をアーカイブします。
    sdk                 評価 SDK plugins を一覧表示して確認します。
    resume              保存済み Suite の未完了処理を継続します。
    retry               元の入力で未完了 Case を再実行します。
    reuse               保存済み Cases を関連付けた新しい Suite で実行します。

オプション：
  -h, --help            このヘルプを表示して終了します
```

各コマンドのオプションは `agentbench COMMAND --help` で確認できます。

## 関連ドキュメント

- [ABB のインストール、設定、実行 — 英語](../README-previous.md)
- [Agent を ABB に追加してテストする方法](How%20To%20Add%20Agent.ja.md)
- [結果とトラブルシューティング — 英語](../Troubleshooting.md)

## ライセンス

MIT。詳細は [LICENSE](../../LICENSE) を参照してください。

# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench — Agent 동작 평가"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文</a> |
  한국어
</p>

<p align="center">
  <img alt="Python 3.10 이상" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package version 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## ABB란 무엇인가요?

AgentBehaviorBench는 AI Agent를 위한 행동 테스트 시스템입니다. 구체적인 작업에서 Agent가
받은 지시, 호출한 모델과 도구, 발생시킨 변경 사항, 수집된 증거가 최종 답변을 뒷받침하는지를
평가합니다.

ABB는 최종 텍스트만 비교하지 않습니다. Case를 통해 안전 경계, 지시 처리, 도구 사용,
상태 변경, Agent가 자신의 행동을 정확하게 보고했는지 등을 검사할 수 있습니다. 각 평가는
Case, Agent 출력, 실행 증거, Judge 결과를 보존합니다.

## 개요

ABB는 서로 다른 프레임워크로 구현된 여러 Agent를 등록하여 하나의 평가 파이프라인에서
실행할 수 있습니다. 평가 SDK는 각 Agent가 선언한 기능을 바탕으로 Cases를 생성합니다.
ABB는 각 Case를 격리된 환경에서 실행하고 모델 호출, 도구 호출, 파일 변경 및 Agent 출력을
수집한 뒤, SDK가 이 증거를 사용하여 관찰된 행동을 판정합니다.

![AgentBehaviorBench 아키텍처](../figures/abb-architecture-v2.png)

Agent Registry는 테스트 대상 소스 리비전과 ABB가 Agent를 시작하는 방법을 기록합니다.
Harness는 Cases를 예약하고, 컨테이너를 시작하고, Agent Run을 실행하고, 선언된 트래픽을
라우팅하며 trace와 파일 시스템 증거를 수집합니다. 실행 상태와 Judge 판정은 별개입니다.
Agent가 정상적으로 실행되더라도 Judge가 행동 문제를 발견할 수 있습니다.

## 현재 가져온 Agents

다음 Agent 소스가 현재 ABB에 등록되어 있습니다.

ABB는 현재 LangGraph Agent의 네이티브 통합과 Agent Client Protocol(ACP)을 통해 제공되는
Agent를 지원합니다.

각 GitHub revision 링크는 `agent.toml`에 고정된 정확한 commit을 가리킵니다. Folder Mover
Agent는 로컬 디렉터리에서 가져왔으므로 ABB는 Git commit 대신 소스 내용 digest를 기록합니다.

| Agent | GitHub 소스 | 선택한 리비전 |
| --- | --- | --- |
| `folder-mover-agent` | 로컬 소스 | `sha256:2826f61…` |
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

`resources/registry.toml`은 Agent 활성화 상태, 준비 상태, Case 수 및 step 제한에 대한
공식 정보원입니다.

## 평가 SDK 및 Judge

공식 평가는 현재 [KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX)를
사용하며 `kuma-defuzex[otel]==0.3.1`로 고정되어 있습니다. KUMA는 행동 테스트 Cases를
생성하고, ABB가 수집한 증거를 받아 DefuzeX Judge에 제출합니다. 판정 및 평가 결과는
Suite artifacts와 함께 저장됩니다.

ABB에는 결정론적 오프라인 개발과 테스트를 위한 `local` SDK plugin도 포함되어 있습니다.
이 plugin은 공식 benchmark 결과에 사용되는 Judge가 아닙니다.

## ABB CLI 도움말

```text
usage: agentbench [-h]
                  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
                  ...

등록된 Benchmark Agents를 실행, 인증 및 검사합니다.

위치 인수:
  {run,agent,view,certify,observe,evaluate,clean,sdk,resume,retry,reuse}
    run                 활성화되고 ready인 모든 Agents를 실행합니다.
    agent               Agent 소스를 가져오고 검사합니다.
    view                저장된 결과를 로컬 뷰어에서 엽니다.
    certify             adapting Agent를 실행하고 성공 후 ready로 승격합니다.
    observe             활성화된 Agent를 실행하고 trace를 저장합니다.
    evaluate            독립적인 SDK Cases로 Agent를 평가합니다.
    clean               참조되지 않는 로컬 결과 기록을 보관합니다.
    sdk                 평가 SDK plugins를 나열하고 검사합니다.
    resume              저장된 Suite의 완료되지 않은 작업을 계속합니다.
    retry               원래 입력으로 완료되지 않은 Case를 다시 실행합니다.
    reuse               저장된 Cases를 연결된 새 Suite에서 실행합니다.

옵션:
  -h, --help            도움말을 표시하고 종료합니다
```

명령별 옵션은 `agentbench COMMAND --help`로 확인할 수 있습니다.

## 추가 문서

- [ABB 설치, 설정 및 실행 — 영어](../README-previous.md)
- [테스트할 Agent를 ABB에 추가하는 방법](How%20To%20Add%20Agent.ko.md)
- [결과 및 문제 해결 — 영어](../Troubleshooting.md)

## 라이선스

MIT. 자세한 내용은 [LICENSE](../../LICENSE)를 참조하세요.

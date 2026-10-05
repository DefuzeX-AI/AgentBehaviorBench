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

AgentBehaviorBench(ABB)는 AI Agent가 다른 Agent의 행동을 테스트하는 능력을 평가하는
벤치마크입니다. 바로 실행할 수 있는 대상 Agents와 사람이 직접 수행한 실제 테스트를 통해 확인한 행동 결함이라는
두 가지 데이터셋을 포함합니다. 확인된 결함은 Ground Truth(정답 데이터)로 사용합니다.
평가에 참여하는 테스트 Agent는 테스트 케이스를 생성하고 대상 Agent가 이를 실행하도록 한 뒤,
그 과정에서 생성된 실행 궤적을 분석하여 대상 Agent의 문제를 찾습니다.

## 개요

ABB는 Adapters를 통해 서로 다른 프레임워크로 구현된 대상 Agents를 연결하고 하나의
파이프라인에서 테스트 케이스를 실행하며 행동 증거를 수집합니다. ABB에 연결하는 테스트
Agent는 테스트 케이스 생성, 실행 증거 분석 및 결함 판정(Judge) 능력을 갖추어야 하며,
평가 SDK를 통해 연결됩니다. 실행 증거에는 테스트 입력, Agent 출력과 실행 상태,
OpenTelemetry 트레이스, 파일 증거 수집을 활성화한 경우의 파일 변경 기록과 Diff가 포함됩니다.
테스트 Agent는 이러한 증거를 바탕으로 행동 결함을 보고해야 합니다. 벤치마크에서
Ground Truth에 지정된 결함을 찾아내면 해당 점수를 받습니다.

AgentBehaviorBench 평가에 참여하는 각 테스트 Agent는 다음 능력을 갖추어야 합니다.

1. **테스트 케이스 생성(Case Generation)**: 대상 Agent의 기능과 행동 제약을 바탕으로 그 행동을 검증하는 테스트 케이스를 생성합니다.
2. **실행 궤적 분석(Trajectory Analysis)**: 테스트 입력, Agent 출력, OpenTelemetry 트레이스 및 파일 변경 증거를 분석하여 잠재적인 행동 이상을 식별합니다.
3. **결함 판정(Judging)**: 실행 증거를 바탕으로 대상 Agent에 행동 결함이 있는지 판단하고, 구체적인 문제와 이를 뒷받침하는 증거를 보고합니다.

![AgentBehaviorBench 아키텍처](../figures/abb-suite-sdk-roles.png)

Agent Registry는 테스트 대상 소스 리비전과 ABB가 Agent를 시작하는 방법을 기록합니다.
Harness는 Cases를 예약하고, 컨테이너를 시작하고, Agent Run을 실행하고, 선언된 트래픽을
라우팅하며 trace와 파일 시스템 증거를 수집합니다. 실행 상태와 Judge 판정은 별개입니다.
Agent가 정상적으로 실행되더라도 Judge가 행동 문제를 발견할 수 있습니다.

## 리소스

- [등록된 Agents](Agents.ko.md) — 대상 Agent 목록, 소스 저장소 및 고정 리비전.
- [Agent 등록부 읽는 방법](Registry.ko.md) — `registry.toml` 필드, Agent 선택 및 Case 예산.
- [Agent 추가 방법](How%20To%20Add%20Agent.ko.md)
- [CLI 문서](cli.ko.md)
- [ABB 시작 방법 — 영어](../Guide.md)

## 평가 SDK 및 Judge

공식 평가는 현재 [KUMA DefuzeX SDK](https://github.com/DefuzeX-AI/KUMA-DefuzeX)를
사용하며 `kuma-defuzex[otel]`로 설치합니다. SDK 설치 단계가 실행되면 PyPI의 최신 안정
버전을 선택합니다. 기존 이미지와 Docker 빌드 레이어는 재사용되며 SDK의 새 버전이
출시되어도 자동으로 업데이트되지 않습니다. KUMA는 행동 테스트 Cases를
생성하고, ABB가 수집한 증거를 받아 DefuzeX Judge에 제출합니다. 판정 및 평가 결과는
Suite artifacts와 함께 저장됩니다.

ABB에는 고정 스모크 테스트 Cases와 로컬 Judge를 사용하는 `local` SDK plugin도 포함되어 있습니다.
KUMA 백엔드 크레딧은 필요하지 않지만 Agent와 Judge 모델 호출에는 비용이 발생할 수 있습니다.
이 plugin은 공식 benchmark 결과에 사용되는 Judge가 아닙니다.


## 추가 문서

- [결과 및 문제 해결 — 영어](../Troubleshooting.md)

## 라이선스

MIT. 자세한 내용은 [LICENSE](../../LICENSE)를 참조하세요.

# `registry.toml` 읽는 방법

[English](../Registry.md) | [中文](Registry.zh-CN.md) | [Français](Registry.fr.md) | [日本語](Registry.ja.md) | 한국어

[README로 돌아가기](README.ko.md) · [ABB 시작 방법 — 영어](../Guide.md)

[Agent 등록부](../../resources/registry.toml)는 ABB에서 사용할 대상 Agents, 로컬 연동
디렉터리 및 기본 평가 예산을 기록합니다. `agentbench run`은 `enabled = true`와
`status = "ready"`를 모두 만족하는 항목을 선택합니다.

## 항목 읽기

파일 첫머리에 형식 버전을 지정하며, 각 `[[agents]]` 블록이 Agent 하나를 등록합니다.

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

이 예시는 LangGraph Agent를 등록하고 기본값으로 독립적인 Case 하나, Case당 최대 세 번의
대화 단계를 설정합니다. `ready`로 표시되어 있지만 비활성 상태이므로 `run`에서 제외됩니다.
`source` 경로는 한 컴퓨터에서 원래 소스를 가져온 위치의 예시입니다. 사용자가 같은
디렉터리를 만들 필요는 없습니다.

| 필드 | 의미 |
| --- | --- |
| `schema_version` | 파일 전체의 형식 식별자입니다. `"defuzex-bench.registry.v1"`을 Agent 블록 앞에 한 번만 작성합니다. |
| `[[agents]]` | TOML의 테이블 배열 문법입니다. 각 블록은 별도의 Agent 등록 항목입니다. |
| `agent_id` | CLI 명령에서 사용하는 고유 식별자입니다. 해당 Agent의 `agent.toml`에 있는 `agent_id`와 일치해야 합니다. |
| `path` | 로컬 연동 디렉터리입니다. 등록부가 표준 위치에 있으면 저장소 루트를 기준으로 해석합니다. 내부 소스 디렉터리 `agent/`가 아니라 `agent.toml`과 `requirement.md`가 있는 바깥 디렉터리를 가리키며, 저장소 안에 있어야 합니다. |
| `enabled` | Agent 선택을 허용하는지 나타냅니다. `false`이면 `run`과 단일 Agent `evaluate` 선택에서 제외됩니다. TOML 불리언을 사용하며 생략 시 기본값은 `true`입니다. |
| `status` | 연동 단계입니다. `adapting`은 인증 대기 상태이며, `ready`는 활성화되어 있으면 기본 `run`에 포함될 수 있음을 나타냅니다. 생략 시 `unknown`이며 `run`에서 제외됩니다. |
| `framework` | `langgraph`, `acp` 등의 프레임워크 표시입니다. 매니페스트 및 실제 연동 방식과 일치시킵니다. 런타임 Adapter와 시작 설정은 `agent.toml`에서 정의합니다. |
| `source` | 저장소 URL이나 로컬 가져오기 디렉터리 등 원래 소스 위치입니다. 변경해도 이미 가져온 코드가 교체되거나 시작 설정이 바뀌지 않습니다. 생략 시 빈 문자열입니다. |
| `case` | 이 Agent에서 실행할 독립적인 Cases 수입니다. 양의 정수여야 하며 생략 시 기본값은 `1`입니다. |
| `step` | SDK에 전달하는 Case당 대화 단계 수 상한입니다. 지정하면 양의 정수여야 하며, 생략하면 SDK 기본값을 사용합니다. 실제 단계 수는 더 적을 수 있습니다. |

`agent_id`, `path`, `framework`는 비어 있지 않은 필수 문자열입니다. TOML의 큰따옴표
문자열에서는 Windows 경로의 역슬래시를 `\\`로 작성합니다.

## `case`와 `step` 구분

- `case = 1`, `step = 3`: 독립적인 Case 하나에 최대 세 번의 순차 입력을 포함합니다.
- `case = 5`, `step = 3`: 독립적인 Cases 다섯 개에 각각 최대 세 번의 입력을 포함합니다.
- 대화 단계 하나는 대상 Agent에 입력 하나를 전달합니다. 실행 중 여러 모델 및 도구 호출이
  발생할 수 있으므로 `step`은 도구 호출 수나 내부 추론 반복 수의 상한이 아닙니다.
  두 필드는 동시 실행 수를 설정하지도 않습니다.

여러 대화 단계를 지원하지 않는 Agent도 있으므로, Benchmark가 각 Agent에 설정한 기본
`step` 값을 유지하는 것을 권장합니다.

선택한 SDK는 생성과 실행 시 단계 예산을 적용합니다. 명시적인 SDK `max_steps` 옵션이
등록부의 `step`보다 우선합니다. `evaluate`에서 `--cases`는 `case`를, `--max-steps`는
단계 예산을 해당 실행에만 덮어쓰며 등록부를 수정하지 않습니다.

```bash
agentbench evaluate react-agent --cases 2 --max-steps 3 --no-view
```

## Agent 선택 및 기본값 변경

예시 Agent를 `run`에 포함하려면 `enabled = true`로 설정합니다. 새로 연동한 `adapting`
Agent는 [연동 설정](How%20To%20Add%20Agent.ko.md)을 완료하고 활성 상태에서 인증합니다.

```bash
agentbench certify folder-mover-agent --no-view
```

인증에 성공하면 `ready`로 변경됩니다. 이 상태는 연동 준비 완료를 나타내며 Judge가 행동
결함을 발견하지 않을 것을 보장하지 않습니다. 상태를 수동으로 바꿔도 인증이 실행되지는
않습니다. `run`과 달리 `evaluate`는 `ready`로 필터링하지 않고 활성 Agent를 선택합니다.

```bash
agentbench observe --list
agentbench run --no-view
```

`case`와 `step`을 변경하면 이후 실행의 기본 예산이 바뀝니다. 저장된 Cases와 결과는 기록된
설정을 유지합니다. `run`은 선택 전에 모든 항목을 검증하므로 비활성 Agent라도 연동 파일이
없으면 등록부 로딩에 실패할 수 있습니다. 유효한 경로, 고유 식별자 및 필수 파일을 유지하세요.
소스 목록은 [등록된 Agents](Agents.ko.md)를 참조하세요.

# ABB CLI 문서

[English](../cli.md) | [中文](cli.zh-CN.md) | [Français](cli.fr.md) | [日本語](cli.ja.md) | 한국어

[README로 돌아가기](README.ko.md) · [ABB 시작 방법 — 영어](../Guide.md) · [Agent 등록부](Registry.ko.md) · [Agent 추가 방법](How%20To%20Add%20Agent.ko.md)

각 명령의 목적, 모든 공개 인자, 기본 동작 및 예제를 설명합니다. 실행 전에 ABB 설치와 대상 Agent 설정을 완료하세요.

AGENT_ID, SUITE_ID, CASE_ID, RUN_ID, 소스 경로와 파일 이름을 실제 값으로 바꾸세요. Agent 번호는 출력 목록 기준이며 Case 번호는 1부터 시작합니다. OPTIONS는 각 표의 옵션을 뜻합니다. 모든 명령은 -h/--help를 지원하며 인자 없는 agentbench는 run을 실행합니다.

```bash
agentbench --help
agentbench evaluate --help
agentbench agent add --help
```

agent 그룹은 add, sdk 그룹은 list 또는 show 하위 명령이 필요합니다. 그룹 도움말은 agentbench agent --help 또는 agentbench sdk --help입니다. 하위 명령 선택 전 그룹 수준에서는 -h/--help만 받습니다.

## 명령 선택

| 명령 | 역할 및 기본 동작 |
| --- | --- |
| `agentbench run` | 등록부에서 활성 상태이고 ready인 모든 Agents를 하나의 Suite로 실행합니다. 각 case 수와 step 예산을 사용하고 실행 전에 선택을 확인합니다. |
| `agentbench evaluate` | 선택한 SDK로 활성 Agent 하나의 독립 Cases를 생성하고 실행·증거 수집·Judge 판정을 수행합니다. certify와 달리 등록부 상태를 변경하지 않습니다. |
| `agentbench agent add` | GitHub 저장소 또는 로컬 디렉터리를 가져옵니다. -b/-c가 없으면 소스 가져오기와 파일 목록만 수행합니다. -b는 설정 생성, -c는 인증이며 함께 사용할 수 있습니다. |
| `agentbench certify` | 활성 adapting Agent의 등록 Case 예산을 실행하고 모든 Cases가 호출 오류 없이 완료되면 ready로 승격합니다. Judge 문제 지적 자체는 승격을 막지 않으며 ready Agent는 재실행하지 않습니다. |
| `agentbench observe` | 네이티브 입력 하나를 실행하고 출력과 트레이스를 저장하며 SDK Case 생성이나 Judge는 사용하지 않습니다. 현재 Docker oneshot 실행이 필요합니다. --list와 --show는 읽기 전용입니다. |
| `agentbench view` | 저장 결과를 로컬 웹 뷰어로 제공합니다. 먼저 웹을 빌드하고 출력된 전체 View URL을 열어 명령을 계속 실행합니다. Ctrl+C로 종료합니다. |
| `agentbench sdk list` | SDK 디렉터리에서 발견한 플러그인 이름을 표시합니다. 모든 실행 의존성이 설치됐는지 확인하는 것은 아닙니다. |
| `agentbench sdk show` | SDK 플러그인을 불러와 출처, 실행 방식 및 자동 선택 가능 여부를 표시합니다. |
| `agentbench resume` | 저장 Cases·설정과 현재 자격 증명으로 Suite의 복구 가능한 미완료 작업을 계속합니다. 새 Cases를 생성하거나 완료된 Cases를 의도적으로 재실행하지 않습니다. |
| `agentbench retry` | 원본 Suite의 미완료 Case 하나를 원래 입력으로 복구합니다. 저장 상태에 따라 요청을 복구하거나 첫 입력부터 재실행하며 재실행 조건은 계속 적용됩니다. |
| `agentbench reuse` | 저장 Case 입력으로 새 Agent 실행·증거 수집·Judge 판정을 수행하고 연결된 재실행 Suite에 저장합니다. 원본 결과를 보존하며 새 입력을 생성하지 않습니다. 완료 Case 재실행에 사용합니다. |
| `agentbench clean` | 프로젝트 results에서 참조되지 않는 최상위 이력을 cache/history-trash로 보관하고 저장 Suites와 참조 산출물을 보존합니다. 먼저 미리 보고 실제 정리 전 실행과 뷰어를 중지합니다. |

## `run`

등록부에서 활성 상태이고 ready인 모든 Agents를 하나의 Suite로 실행합니다. 각 case 수와 step 예산을 사용하고 실행 전에 선택을 확인합니다.

```text
agentbench run [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `--sdk NAME` | sdk list의 디렉터리 이름으로 SDK를 선택합니다. 기본 제공값은 kuma이며 local은 명시해야 합니다. 자동 선택 가능한 플러그인이 여러 개면 이름을 지정합니다. | `--sdk kuma` |
| `--sdk-options PATH` | 선택한 SDK 옵션을 JSON 객체 파일에서 읽습니다. 생략하면 SDK 기본값을 사용합니다. | `--sdk-options sdk-options.json` |
| `--case-retries N` | 안전하게 복구 가능한 Case 실패의 추가 자동 시도 수입니다. 0 이상 정수, 기본값 2이며 0은 자동 재시도를 끕니다. | `--case-retries 0` |
| `--retry-delay SECONDS` | 첫 재시도 대기 시간(초)입니다. 유한한 0 이상 숫자, 기본값 5이며 후속 대기는 재시도 정책에 따라 늘어납니다. | `--retry-delay 5` |
| `-y, --yes` | 실행 확인을 생략합니다. 기본적으로 확인을 요청합니다. | `--yes` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--results-dir DIR` | ABB 결과 루트를 지정하며 없으면 생성합니다. 저장소 루트에서 기본값은 results/입니다. 이벤트는 DIR/suites/SUITE_ID/events.json에 저장됩니다. 이전 결과 위치 옵션과 함께 사용할 수 없습니다. | `--results-dir results/my-run` |
| `--output PATH` | 이전 ABB 결과 위치 옵션입니다. 파일 경로는 부모 디렉터리만 선택하며 해당 파일을 생성하지 않습니다. --results-dir를 권장합니다. 저장소 루트에서 기본값은 results/입니다. | `--output results/legacy.json` |
| `--no-view` | 결과를 저장하되 웹 뷰어를 시작하지 않습니다. 기본적으로 뷰어를 시작하거나 재사용하므로 웹 빌드가 필요합니다. | `--no-view` |
| `--model MODEL` | ABB 대체 대상 모델을 덮어씁니다. 기본값은 선택한 서비스 설정이며 네이티브 ACP 모델은 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | 스트리밍 메모리 임시 저장의 이전 임계값입니다. 단위 바이트, 기본값 262144(256 KiB)이며 저장 내용을 잘라내지 않습니다. | `--llm-trace-max-bytes 262144` |

run에는 --registry, --cases, --max-steps가 없습니다. Agent별 기본 예산은 등록부에서 수정하며 SDK JSON max_steps로 단계 예산을 덮어쓸 수 있습니다.

### 예제

```bash
agentbench run --sdk kuma
agentbench run --sdk local --yes --no-view --results-dir results/smoke
```

## `evaluate`

선택한 SDK로 활성 Agent 하나의 독립 Cases를 생성하고 실행·증거 수집·Judge 판정을 수행합니다. certify와 달리 등록부 상태를 변경하지 않습니다.

```text
agentbench evaluate [AGENT] [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `-y, --yes` | 실행 확인을 생략합니다. 기본적으로 확인을 요청합니다. | `--yes` |
| `AGENT` | 활성 Agent ID 또는 메뉴 번호입니다. 생략하면 대화식으로 선택하며 --yes 사용 시 지정해야 합니다. ready 상태는 필수가 아닙니다. | `react-agent` |
| `--registry PATH` | Agent 등록부를 지정합니다. 기본값은 프로젝트의 resources/registry.toml입니다. | `--registry resources/registry.toml` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--model MODEL` | ABB 대체 대상 모델을 덮어씁니다. 기본값은 선택한 서비스 설정이며 네이티브 ACP 모델은 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--sdk NAME` | sdk list의 디렉터리 이름으로 SDK를 선택합니다. 기본 제공값은 kuma이며 local은 명시해야 합니다. 자동 선택 가능한 플러그인이 여러 개면 이름을 지정합니다. | `--sdk kuma` |
| `--sdk-options PATH` | 선택한 SDK 옵션을 JSON 객체 파일에서 읽습니다. 생략하면 SDK 기본값을 사용합니다. | `--sdk-options sdk-options.json` |
| `--case-retries N` | 안전하게 복구 가능한 Case 실패의 추가 자동 시도 수입니다. 0 이상 정수, 기본값 2이며 0은 자동 재시도를 끕니다. | `--case-retries 0` |
| `--retry-delay SECONDS` | 첫 재시도 대기 시간(초)입니다. 유한한 0 이상 숫자, 기본값 5이며 후속 대기는 재시도 정책에 따라 늘어납니다. | `--retry-delay 5` |
| `--no-view` | 결과를 저장하되 웹 뷰어를 시작하지 않습니다. 기본적으로 뷰어를 시작하거나 재사용하므로 웹 빌드가 필요합니다. | `--no-view` |
| `--llm-trace-max-bytes BYTES` | 스트리밍 메모리 임시 저장의 이전 임계값입니다. 단위 바이트, 기본값 262144(256 KiB)이며 저장 내용을 잘라내지 않습니다. | `--llm-trace-max-bytes 262144` |
| `--results-dir DIR` | ABB 결과 루트를 지정하며 없으면 생성합니다. 저장소 루트에서 기본값은 results/입니다. 이벤트는 DIR/suites/SUITE_ID/events.json에 저장됩니다. 이전 결과 위치 옵션과 함께 사용할 수 없습니다. | `--results-dir results/my-run` |
| `--result-output PATH` | 이전 ABB 결과 위치입니다. 파일을 생성하지 않고 부모 디렉터리를 선택합니다. --results-dir를 권장하며 둘은 함께 사용할 수 없습니다. 기본값은 프로젝트 results/입니다. | `--result-output results/legacy.json` |
| `--output DIR` | SDK 산출물 디렉터리로 ABB Suite 결과와 별개입니다. SDK JSON output을 덮어쓰며 KUMA/local 기본값은 results/observe입니다. | `--output results/sdk-artifacts` |
| `--timeout SECONDS` | SDK 실행 제한 시간(초)이며 유한한 양수입니다. SDK JSON timeout을 덮어씁니다. KUMA/local 기본값은 2400이며 다른 SDK는 자체 정의합니다. | `--timeout 2400` |
| `--cases N` | 독립적인 Cases 수이며 양의 정수입니다. 기본값은 등록부의 case이고 해당 실행에만 적용하며 등록부를 수정하지 않습니다. | `--cases 1` |
| `--max-steps N` | Case당 SDK 대화 단계 상한이며 양의 정수입니다. 등록부 step과 SDK JSON의 max_steps를 덮어씁니다. 단일 단계만 지원하는 Agent도 있습니다. | `--max-steps 3` |

### 예제

```bash
agentbench evaluate react-agent --sdk kuma --cases 1
agentbench evaluate react-agent --sdk local --cases 1 --yes --no-view --results-dir results/smoke
agentbench evaluate react-agent --sdk kuma --cases 2 --max-steps 3 --output results/sdk-artifacts --results-dir results/my-run --no-view
```

## `agent add`

GitHub 저장소 또는 로컬 디렉터리를 가져옵니다. -b/-c가 없으면 소스 가져오기와 파일 목록만 수행합니다. -b는 설정 생성, -c는 인증이며 함께 사용할 수 있습니다.

```text
agentbench agent add SOURCE [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `SOURCE` | HTTPS GitHub 저장소 URL 또는 로컬 절대 디렉터리가 필수입니다. 브랜치/파일 URL은 허용하지 않습니다. 일반 가져오기는 단위를 생성하며 -b/-c는 일치하는 소스를 재사용할 수 있습니다. | `https://github.com/langchain-ai/react-agent` |
| `--agents-dir DIR` | 번호가 붙은 Agent 단위의 부모 디렉터리입니다. 기본값은 프로젝트 기본 등록부 옆 resources/agents입니다. 생성 단위는 --registry의 루트 안에 있어야 합니다. | `--agents-dir resources/agents` |
| `-b, --build` | 연동 설정을 생성·검증·저장하고 adapting으로 등록합니다. 유효한 완료 파일을 재사용하며 LangGraph와 ACP를 지원합니다. Docker를 빌드하지 않습니다. 기본값은 꺼짐입니다. | `-b` |
| `-c, --certify` | 생성되거나 수동 준비한 연동을 검증·등록한 뒤 인증합니다. -b를 자동 활성화하지 않습니다. 기본값은 꺼짐입니다. | `-c` |
| `--registry PATH` | Agent 등록부를 지정합니다. 기본값은 프로젝트의 resources/registry.toml입니다. | `--registry resources/registry.toml` |
| `--build-settings PATH` | [build] 테이블의 TOML 파일로 생성 예산과 모델 등을 덮어씁니다. 기본값은 내장 설정이며 -b와 함께 사용합니다. | `--build-settings build-settings.toml` |
| `--build-model MODEL` | -b 설정 생성용 OpenRouter 모델입니다. 우선순위는 이 옵션, [build].model, OPENROUTER_BUILD_MODEL, OPENROUTER_MODEL이며 구조화 출력 지원이 필요합니다. | `--build-model openai/gpt-4.1-mini` |
| `--answers PATH` | 이전 생성 계획 질문에 대한 UTF-8 답변 파일입니다. 파일과 함께 -b를 다시 실행합니다. 기본값은 답변 파일 없음입니다. | `--answers answers.txt` |
| `--with-observe` | -b와 함께 observe 대화식 입력 필드를 생성합니다. 기본값은 꺼짐이며 -b 없이는 허용되지 않습니다. | `--with-observe` |
| `--agent-timeout SECONDS` | -b에서 생성 Agent의 실행 제한 시간(초)을 설정합니다. 유한한 양수, 기본값 300이며 생성 요청의 제한 시간은 아닙니다. | `--agent-timeout 600` |
| `--adapter-context PATH` | -b에서 명시적인 배포 컨텍스트 JSON 객체를 읽습니다. 최대 64 KiB이며 기본값은 덮어쓰기 없음입니다. 내용은 Agent 연동 방식과 일치해야 합니다. | `--adapter-context adapter-context.json` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--model MODEL` | -c 인증의 대체 대상 모델이며 --build-model과 독립적입니다. 기본값은 서비스 설정이고 네이티브 ACP 모델은 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--output PATH` | -c 인증 결과 위치입니다. 관리 Suite에서는 파일을 생성하지 않고 부모 디렉터리를 선택합니다. 기본값은 프로젝트 results/이며 이 명령에는 --results-dir 옵션이 없습니다. | `--output results/add-certification.json` |
| `--no-view` | -c에서 인증 결과를 저장하되 뷰어를 시작하지 않습니다. 소스 가져오기와 설정 생성에는 영향이 없습니다. 기본값은 인증 뷰어 사용입니다. | `--no-view` |
| `-y, --yes` | -c 인증 실행 확인을 생략합니다. 기본적으로 확인하며 생성 계획 질문에 자동 답변하지는 않습니다. | `--yes` |
| `--sdk NAME` | sdk list의 디렉터리 이름으로 SDK를 선택합니다. 기본 제공값은 kuma이며 local은 명시해야 합니다. 자동 선택 가능한 플러그인이 여러 개면 이름을 지정합니다. | `--sdk kuma` |
| `--sdk-options PATH` | SDK 옵션 JSON 객체를 읽습니다. -c 인증에만 적용하며 -b 생성에는 사용하지 않습니다. 생략하면 SDK 기본값을 사용합니다. | `--sdk-options sdk-options.json` |

로컬 경로는 절대 경로여야 하며 Windows에서는 "C:\work\local-agent"를 사용할 수 있습니다. -d는 허용되지 않습니다. 생성은 OpenRouter와 온보딩 검증 인터페이스가 있는 SDK를 요구하며 local은 제공하지 않습니다.

### 예제

```bash
agentbench agent add https://github.com/langchain-ai/react-agent
agentbench agent add /absolute/path/to/local-agent -b --sdk kuma --build-model openai/gpt-4.1-mini
agentbench agent add /absolute/path/to/local-agent -b -c --sdk kuma --no-view
```

## `certify`

활성 adapting Agent의 등록 Case 예산을 실행하고 모든 Cases가 호출 오류 없이 완료되면 ready로 승격합니다. Judge 문제 지적 자체는 승격을 막지 않으며 ready Agent는 재실행하지 않습니다.

```text
agentbench certify AGENT_ID [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `-y, --yes` | 실행 확인을 생략합니다. 기본적으로 확인을 요청합니다. | `--yes` |
| `--registry PATH` | Agent 등록부를 지정합니다. 기본값은 프로젝트의 resources/registry.toml입니다. | `--registry resources/registry.toml` |
| `--sdk NAME` | sdk list의 디렉터리 이름으로 SDK를 선택합니다. 기본 제공값은 kuma이며 local은 명시해야 합니다. 자동 선택 가능한 플러그인이 여러 개면 이름을 지정합니다. | `--sdk kuma` |
| `--sdk-options PATH` | 선택한 SDK 옵션을 JSON 객체 파일에서 읽습니다. 생략하면 SDK 기본값을 사용합니다. | `--sdk-options sdk-options.json` |
| `--case-retries N` | 안전하게 복구 가능한 Case 실패의 추가 자동 시도 수입니다. 0 이상 정수, 기본값 2이며 0은 자동 재시도를 끕니다. | `--case-retries 0` |
| `--retry-delay SECONDS` | 첫 재시도 대기 시간(초)입니다. 유한한 0 이상 숫자, 기본값 5이며 후속 대기는 재시도 정책에 따라 늘어납니다. | `--retry-delay 5` |
| `--no-view` | 결과를 저장하되 웹 뷰어를 시작하지 않습니다. 기본적으로 뷰어를 시작하거나 재사용하므로 웹 빌드가 필요합니다. | `--no-view` |
| `AGENT_ID` | 활성 등록 Agent의 정확한 ID가 필수입니다. adapting Agent를 인증하며 ready Agent는 재실행 없이 반환합니다. | `folder-mover-agent` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--results-dir DIR` | ABB 결과 루트를 지정하며 없으면 생성합니다. 저장소 루트에서 기본값은 results/입니다. 이벤트는 DIR/suites/SUITE_ID/events.json에 저장됩니다. 이전 결과 위치 옵션과 함께 사용할 수 없습니다. | `--results-dir results/my-run` |
| `--output PATH` | 이전 ABB 결과 위치 옵션입니다. 파일 경로는 부모 디렉터리만 선택하며 해당 파일을 생성하지 않습니다. --results-dir를 권장합니다. 저장소 루트에서 기본값은 results/입니다. | `--output results/legacy.json` |
| `--model MODEL` | ABB 대체 대상 모델을 덮어씁니다. 기본값은 선택한 서비스 설정이며 네이티브 ACP 모델은 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | 스트리밍 메모리 임시 저장의 이전 임계값입니다. 단위 바이트, 기본값 262144(256 KiB)이며 저장 내용을 잘라내지 않습니다. | `--llm-trace-max-bytes 262144` |

### 예제

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
agentbench certify AGENT_ID --sdk local --yes --no-view --results-dir results/certification
```

## `observe`

네이티브 입력 하나를 실행하고 출력과 트레이스를 저장하며 SDK Case 생성이나 Judge는 사용하지 않습니다. 현재 Docker oneshot 실행이 필요합니다. --list와 --show는 읽기 전용입니다.

```text
agentbench observe [AGENT] [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `AGENT` | 활성 Agent ID 또는 메뉴 번호입니다. 생략하면 대화식 선택이며 --agent와 함께 사용할 수 없습니다. | `react-agent` |
| `--agent AGENT` | 위치 인자 대신 Agent ID 또는 메뉴 번호를 지정합니다. 두 방식은 함께 사용할 수 없습니다. | `--agent react-agent` |
| `--registry PATH` | Agent 등록부를 지정합니다. 기본값은 프로젝트의 resources/registry.toml입니다. | `--registry resources/registry.toml` |
| `--list` | 활성 Agents를 표시하고 실행 없이 종료합니다. 기본값은 꺼짐입니다. | `--list` |
| `--input PATH` | UTF-8 JSON에서 네이티브 입력 하나를 읽습니다. 텍스트는 따옴표가 있는 JSON 문자열입니다. 기본값은 observe 필드 또는 JSON 대화식 입력입니다. | `--input native-input.json` |
| `--output DIR` | Observe 산출물 루트입니다. 실행 ID별 하위 디렉터리를 생성하며 기본값은 results/observe입니다. | `--output results/observe` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--model MODEL` | ABB 대체 대상 모델을 덮어씁니다. 기본값은 선택한 서비스 설정이며 네이티브 ACP 모델은 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--timeout SECONDS` | Agent 실행 제한 시간(초)을 유한한 양수로 덮어씁니다. 기본값은 Agent 실행 설정입니다. | `--timeout 300` |
| `--show DIR` | 저장된 observe 실행을 오프라인으로 확인하고 종료합니다. Agent를 실행하지 않으며 다른 실행 옵션을 사용하지 않습니다. | `--show results/observe/RUN_ID` |

### 예제

```bash
agentbench observe --list
agentbench observe react-agent --input native-input.json --output results/observe --timeout 300
agentbench observe --show results/observe/RUN_ID
```

## `view`

저장 결과를 로컬 웹 뷰어로 제공합니다. 먼저 웹을 빌드하고 출력된 전체 View URL을 열어 명령을 계속 실행합니다. Ctrl+C로 종료합니다.

```text
agentbench view RESULT_LOG [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `RESULT_LOG` | 기존 JSON 결과 파일이 필수입니다. 보통 Result saved의 events.json이며 디렉터리 대신 파일을 전달합니다. | `results/suites/SUITE_ID/events.json` |
| `--host ADDRESS` | 뷰어 수신 주소입니다. 기본값은 127.0.0.1입니다. | `--host 127.0.0.1` |
| `--port N` | 수신 포트는 0–65535이며 기본값은 8765입니다. 0은 자동 할당이고 기본 포트가 사용 중이면 다른 포트를 선택할 수 있습니다. | `--port 0` |

### 예제

```bash
agentbench view results/suites/SUITE_ID/events.json
agentbench view results/suites/SUITE_ID/events.json --host 127.0.0.1 --port 0
```

## `sdk list`

SDK 디렉터리에서 발견한 플러그인 이름을 표시합니다. 모든 실행 의존성이 설치됐는지 확인하는 것은 아닙니다.

```text
agentbench sdk list [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |

### 예제

```bash
agentbench sdk list
```

## `sdk show`

SDK 플러그인을 불러와 출처, 실행 방식 및 자동 선택 가능 여부를 표시합니다.

```text
agentbench sdk show NAME [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `NAME` | SDK 디렉터리 이름이 필수이며 대소문자를 구분하지 않습니다. sdk list의 이름을 사용합니다. | `kuma` |

### 예제

```bash
agentbench sdk show kuma
agentbench sdk show local
```

## `resume`

저장 Cases·설정과 현재 자격 증명으로 Suite의 복구 가능한 미완료 작업을 계속합니다. 새 Cases를 생성하거나 완료된 Cases를 의도적으로 재실행하지 않습니다.

```text
agentbench resume SUITE [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `SUITE` | 저장된 Suite ID, 디렉터리 또는 events.json 경로가 필수입니다. ID는 --suite-root에서 해석합니다. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Suite ID 디렉터리를 포함하는 부모 디렉터리입니다. 기본값은 현재 작업 디렉터리의 results/suites입니다. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |

### 예제

```bash
agentbench resume results/suites/SUITE_ID
agentbench resume SUITE_ID --suite-root results/my-run/suites --env-file .env.testing
```

## `retry`

원본 Suite의 미완료 Case 하나를 원래 입력으로 복구합니다. 저장 상태에 따라 요청을 복구하거나 첫 입력부터 재실행하며 재실행 조건은 계속 적용됩니다.

```text
agentbench retry SUITE --agent ID --case N [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `SUITE` | 저장된 Suite ID, 디렉터리 또는 events.json 경로가 필수입니다. ID는 --suite-root에서 해석합니다. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Suite ID 디렉터리를 포함하는 부모 디렉터리입니다. 기본값은 현재 작업 디렉터리의 results/suites입니다. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--agent ID` | 원본 Suite의 정확한 Agent ID가 필수이며 메뉴 번호가 아닙니다. | `--agent react-agent` |
| `--case N` | 1부터 시작하는 양의 정수 Case 번호가 필수이며 --agent의 해당 Case를 대상으로 합니다. | `--case 1` |

### 예제

```bash
agentbench retry results/suites/SUITE_ID --agent react-agent --case 1
```

## `reuse`

저장 Case 입력으로 새 Agent 실행·증거 수집·Judge 판정을 수행하고 연결된 재실행 Suite에 저장합니다. 원본 결과를 보존하며 새 입력을 생성하지 않습니다. 완료 Case 재실행에 사용합니다.

```text
agentbench reuse SOURCE [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `SOURCE` | 저장된 Suite ID/경로, Case ID, artifact run ID, case.json 또는 시도 경로가 필수입니다. Suite는 기본적으로 모든 Cases를 선택하며 --agent와 --case로 하나를 지정합니다. 중복 ID는 출처를 명시합니다. | `CASE_ID` |
| `--suite-root DIR` | 저장된 Suite 검색을 이 디렉터리로 제한합니다. 기본값은 프로젝트 results와 등록된 외부 Suites입니다. | `--suite-root results/my-run/suites` |
| `--agent ID` | Suite 출처에서 정확한 Agent ID를 선택합니다. --case와 함께 사용해야 하며 둘 다 생략하면 모든 Cases를 재실행합니다. | `--agent react-agent` |
| `--case N` | Suite의 1부터 시작하는 양의 정수 Case 번호이며 --agent와 함께 사용합니다. 직접 Case ID와 혼용하지 않습니다. | `--case 2` |
| `--output-root DIR` | 재실행 Suites의 부모 디렉터리입니다. 새 Suite는 DIR/SUITE_ID에 저장하며 기본값은 원본 Suite의 부모입니다. 이 디렉터리 바로 아래의 호환되는 활성 재실행 Suite에만 참여합니다. | `--output-root results/reruns` |
| `--env-file PATH` | 환경 파일을 지정합니다. 기본값은 프로젝트의 .env이며 셸 환경 변수가 우선합니다. | `--env-file .env.testing` |
| `--model MODEL` | 새 평가의 대체 대상 모델입니다. 기본값은 저장된 모델 설정이며 네이티브 ACP는 Agent 설정을 따릅니다. | `--model openai/gpt-4.1-mini` |
| `--max-steps N` | 새 평가의 SDK 대화 단계 예산이며 양의 정수입니다. 기본값은 저장된 실행 설정이고 저장 Case에 추가 입력을 생성하지 않습니다. | `--max-steps 3` |

호환 요청은 활성 재실행 Suite에 참여할 수 있으며 의도적인 요청마다 새 실행이 추가됩니다. --no-view, --yes, --sdk, --cases 옵션은 없고 결과/뷰어 링크를 출력합니다.

### 예제

```bash
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent react-agent --case 2
agentbench reuse results/suites/SUITE_ID --output-root results/reruns --max-steps 3
```

## `clean`

프로젝트 results에서 참조되지 않는 최상위 이력을 cache/history-trash로 보관하고 저장 Suites와 참조 산출물을 보존합니다. 먼저 미리 보고 실제 정리 전 실행과 뷰어를 중지합니다.

```text
agentbench clean [OPTIONS]
```

| 인자 | 역할 및 기본 동작 | 예제 |
| --- | --- | --- |
| `-h, --help` | 현재 명령의 도움말을 표시하고 종료합니다. | `--help` |
| `--dry-run` | 파일을 이동하지 않고 보관 후보를 표시합니다. 기본값은 꺼짐입니다. | `--dry-run` |
| `-y, --yes` | 보관 확인을 생략합니다. 기본적으로 확인하며 실제 정리 전 실행과 뷰어를 중지합니다. | `--yes` |

### 예제

```bash
agentbench clean --dry-run
agentbench clean
```

## 예제에서 사용하는 파일

해당 인자 사용 전 파일을 생성하세요. JSON은 유효해야 하며 sdk-options.json은 객체여야 합니다. 다음 SDK 옵션은 kuma/local용이며 다른 플러그인은 다른 키를 지원할 수 있습니다.

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

native-input.json은 Agent 네이티브 입력 형식에 맞아야 합니다. answers.txt에는 계획 질문의 실제 답변을 작성합니다. adapter-context.json은 -b 배포 컨텍스트 객체이며 Agent별 필드가 달라 공통 복사 객체는 없습니다.

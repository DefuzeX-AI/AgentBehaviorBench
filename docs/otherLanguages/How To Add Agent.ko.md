# Agent 추가

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | [中文](How%20To%20Add%20Agent.zh-CN.md) | 한국어

**환경 → 소스 가져오기 → 설정 → 정적 검토 → local 스모크 테스트 → KUMA → view →
인계 또는 인증** 순서로 진행합니다. 현재 ABB checkout의 루트에서 해당 가상 환경을 활성화해
명령을 실행하세요. `SOURCE`, `AGENT_ID`, `NN-name`, 결과 경로는 실제 출력값으로 바꿉니다.

Coding agent는 먼저 `AGENTS.md`, 통합 issue, 원본 설치 지침을 읽어야 합니다. 작업 범위,
현재 checkout, `git status`를 기록하고 관련 없는 변경을 보존하세요. README만으로 실행
가능하다고 판단하지 마세요.

**중단 시점:** 사용자가 단계별 승인을 요청했다면 각 단계의 명령, 결과, 증거 경로, 다음 작업을
보고하고 동의를 기다립니다. 그렇지 않으면 승인된 범위에서 매번 재확인하지 않고 진행합니다.
새로운 유료/외부 작업 전에는 모델 호출과 소스 문맥, profile, 평가 증거를 설정된 서비스로
보내는 행위가 승인에 포함되는지 확인합니다. 기존 승인은 유효합니다. 인증 정보나 필수 결정이
없거나, 배포가 지원되지 않거나, 실패 원인이 해결되지 않았다면 이에 의존하는 다음 작업을
중단하고 완료된 결과를 보존하세요. 키나 `.env` 내용을 출력하지 마세요. 체크포인트는 증거
확인이며 반드시 사용자에게 허락을 묻는 절차는 아닙니다.

## 1. 환경 설정

### ABB와 호스트 의존성 설치

먼저 [ABB 설치](README.ko.md)를 완료하세요. Git, Python 3.10+, 활성화된 가상 환경이 필요하며,
인증에는 현재 사용자가 접근할 수 있는 Docker가 필요합니다. 선택한 SDK의 호스트 검증 의존성을 설치합니다.

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
python -m agentbench --help
python -m agentbench sdk list
docker info
```

sdk list에 kuma가 표시되어야 하며 ABB를 실행하는 사용자로 docker info가 성공해야 합니다.
다운로드와 설정 생성만 할 때는 Docker가 필요 없지만 -c 인증에는 필요합니다.
호스트 SDK와 평가 컨테이너 내부 SDK는 별도로 설치됩니다.

유료 서비스를 설정하기 전에 harness를 확인합니다.

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

예상 결과는 `Case execution: 1/1 completed | Judge: pass=1`입니다. 정확한
`OFFLINE_RESULT=` 경로를 보존하세요. 결정적 echo demo는 Docker, 키, 모델이 필요 없고 대상
Agent를 테스트하는 것도 아닙니다. 실패하면 호스트 환경부터 고칩니다. 체크포인트에서는 checkout
경로/revision, CLI/SDK 발견, demo 결과를 보고합니다. SDK 발견은 온보딩 지원의 증명이 아닙니다(2절).

### 인증 정보와 모델 설정

.env가 없을 때만 템플릿을 복사합니다.

```bash
test -f .env || cp .env.example .env
```

로컬에서 파일을 수정하세요.

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **KUMA key**: 전략 카탈로그 조회, Case 생성 및 Judge에 필요합니다. ABB는 DEFUZEX_API_KEY도
  허용하지만 비어 있지 않은 KUMA_API_KEY가 우선합니다.
- **OpenRouter key와 모델**: 통합 파일 생성과 Agent 실행에 사용합니다. 생성 모델은 **엄격한 구조화
  출력**을 지원해야 합니다. 일반 채팅이 되는 모델이라고 설정 생성에도 적합한 것은 아닙니다.
  예시 모델 이름은 설정 예시이며 코드의 암묵적인 기본값이 아닙니다.
- **Agent 의존성**: 원본 저장소 지침에 따라 도구 key, 데이터와 외부 서비스를 준비하세요.
  DB 드라이버 설치는 DB 실행이 아니며 Agent 다운로드가 전체 서비스를 배포하지는 않습니다.

key 발급 링크는 [설정 가이드(영어)](../README-previous.md#configure-a-real-evaluation)에 있습니다.
셸에서 export한 변수가 .env보다 우선하며 --env-file PATH로 다른 파일을 선택할 수 있습니다.
CLI는 선언된 인증 정보를 처리하며 .env 전체를 컨테이너에 마운트하지 않습니다.
실제 key를 소스나 생성 설정에 넣지 마세요.

### 필요한 경우 뷰어 준비

npm과 Node.js **20.x의 20.19 이상 또는 22.12 이상**을 설치한 후 실행합니다.

```bash
cd web
npm ci
npm run build
cd ..
```

이는 ABB 뷰어를 준비하며 Agent 자체의 브라우저나 Node/MCP 의존성은 설치하지 않습니다.
화면이 필요 없으면 아래 추가 명령에 --no-view를 붙이세요. 헤드리스 실행에는 Node나 web/dist가 필요 없습니다.

## 2. 소스를 가져온 뒤 설정 생성

모델 호출 전에 검토할 수 있도록 먼저 가져오기만 실행합니다.

```bash
python -m agentbench agent add https://github.com/owner/repository
```

`SOURCE`는 HTTPS 저장소 자체 URL이며 파일 또는 `/tree/branch` URL이 아닙니다.
`/absolute/path/to/local-agent`, PowerShell의 `C:\work\local-agent` 같은 로컬 절대
디렉터리도 가능하며 `-d`는 필요 없습니다. GitHub는 기본 브랜치 revision을 사용하고
`--revision` 옵션은 없습니다. 로컬 가져오기는 `.git`을 제외하고 SHA-256을 기록합니다.
동일한 정규화 소스에 대한 후속 호출은 unit을 재사용하며 변경된 로컬 소스를 다시 복사하지 않습니다.

**확인 — 가져오기 완료:** 실제 unit 경로와 `source-manifest.json` revision을 기록합니다.
원본 진입점, prompt, 도구, 입력/상태 schema, UI 호출 방식, Python 제약, lockfile을 읽으세요.
외부 서비스와 배포할 인터페이스를 확인합니다. 텍스트 graph는 PDF 업로드 UI와 다릅니다.
가져오기만으로 실행 가능한 Agent가 등록되지는 않습니다. 공식 `agent add`를 건너뛰고
대체 구현을 레지스트리에 직접 넣지 마세요.

배포 조건을 파악한 뒤 같은 소스로 생성합니다.

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view
```

`-b`는 계획, 생성, 검증, `adapting` 등록을 수행하며 **Docker를 빌드하지 않습니다**.
KUMA는 계획 전에 최신 카탈로그를 조회합니다. 목적, 가용성, 정확한 버전, 증거 능력 요건을
검토하고 해당 스냅샷을 보존하세요. 다른 Agent의 전략 ID를 복사하지 마세요. 조회 실패 시
인증 정보나 연결을 해결할 때까지 멈추고 선택값을 지어내지 마세요.

계획에서 정보를 요구하면 사실에 근거한 답을 로컬 UTF-8 파일에 저장하고 재개합니다.

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view --answers answers.txt
```

텍스트/네이티브 입력 매핑, 세션 수명, 제외되는 UI 기능, 서비스와 의존성을 설명하며 업무
입력을 만들어내지 마세요. 재시도 전 `build-result.json`과 실패한 `steps/`를 읽으세요.
완료된 파일은 유지하고 재검증하며 수동 변경 충돌은 생성을 멈춥니다. 전체 진행 상태를 삭제하거나
원인이 그대로인데 유료 요청을 반복하지 마세요.

**현재 revision의 제한:** `local` SDK는 평가를 지원하지만 온보딩 요구사항/검증 hook이 없습니다.
`add -b --sdk local`은 `Selected SDK has no onboarding requirements and validation`으로
중단됩니다. 여기서는 KUMA로 생성하고 5절의 local 평가를 사용합니다. KUMA 인증 정보가
없으면 자동 생성을 중단하세요. local 생성 지원은 별도 코드 변경이며 다른 checkout의 수정이
현재 저장소에도 있다고 가정하면 안 됩니다.

아래 통합 명령은 배포를 이미 이해했고 중간 승인 없이 생성과 인증을 진행하도록 승인받은 경우만 사용합니다.

```bash
python -m agentbench agent add https://github.com/owner/repository -b -c --sdk kuma --no-view
```

`-c`는 빌드와 인증 실행이며 유료 호출이 발생할 수 있습니다. 정적 검사가 아니며 수동 준비
설정에도 사용할 수 있습니다. 현재 자동 생성은 LangGraph를 지원합니다. 미지원 framework를
LangGraph라고 이름만 바꾸지 마세요.

| 옵션 | 용도 |
| --- | --- |
| `--sdk kuma` / `--sdk local` | 명시적으로 선택. 발견된 SDK라고 생성까지 지원하는 것은 아닙니다. |
| `--no-view` | 뷰어를 실행하지 않고 결과 저장. |
| `--build-model MODEL` | 엄격한 구조화 출력을 지원하는 설정 생성 모델. |
| `--model MODEL` | 인증에 사용할 Agent 모델. |
| `--answers answers.txt` | 이전 계획의 질문에 답변. |
| `--with-observe` | `-b`와 함께 observe의 네이티브 입력 안내 생성. |
| `--build-settings settings.toml` | `[build]` 테이블로 설정 변경. |
| `-y` | 실행이 이미 승인된 경우에만 CLI 확인 생략. |

생성 모델 우선순위는 `--build-model`, settings `model`, `OPENROUTER_BUILD_MODEL`,
`OPENROUTER_MODEL`입니다. 예산이나 재시도를 바꾸기 전에
[기본 설정(영문)](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)을 확인하세요.

## 3. 파일별 역할 확인

Agent 단위는 `resources/agents/NN-name/`에 위치합니다. 가져온 소스 주변에 통합 파일이 생성되므로
명령을 실행하기 전에 모든 파일을 직접 만들 필요는 없습니다.

```text
resources/agents/NN-name/
├── agent/                   # 가져온 업스트림 또는 로컬 소스 스냅샷
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 자체 소스

가져온 업스트림 또는 로컬 소스 스냅샷이 들어 있습니다. 실제 그래프, 추론과 도구 구현은 여기에 유지합니다.
ABB 통합 파일을 바깥에 두어 통합 과정에서 원래 동작을 몰래 대체하지 않도록 합니다.

### `agent.toml` — ABB의 시작 및 호출 설정

ID, 프레임워크, 소스 revision, Docker 빌드/시작 설정, 어댑터, 입출력 매핑, 환경 및 모델/도구
경로를 정의합니다. 진입점 경로와 필수 입력을 실제 코드와 대조하세요. 경로나 변수 선언이 도구를
구현하거나 서비스를 실행하지는 않습니다.

### `bindings/*.py` — 네이티브 입출력과의 경계

인수가 없는 동기 팩토리에서 실제 호출 가능한 Agent를 반환합니다. 소스에 근거한 형식 변환과
생명주기 정리를 담당합니다. 답변을 꾸미거나 간소화된 Agent로 바꿔 테스트를 통과시키면 안 됩니다.
Python 문법이 유효하다는 사실만으로 그래프 로딩과 실행이 입증되지는 않습니다.

### `Dockerfile` — 컨테이너 내부 설치

Agent의 Python/시스템 의존성을 설치하고 소스, binding, 설정을 복사합니다. CPU 아키텍처,
인터프리터, 쓰기 가능한 위치, Agent 자체의 브라우저/Node 요구사항을 확인하세요.
현재 KUMA overlay는 python -m pip로 SDK를 설치하므로 선택된 Python에 pip가 필요합니다.

### `.dockerignore` — 빌드에서 제외할 파일

인증 정보, 호스트 venv, 캐시와 결과를 제외하고 이미지에 필요한 소스와 설정은 유지합니다.
-b가 ABB 템플릿으로 생성합니다.

### `requirement.md` — 평가할 내용

배포된 Agent의 목적, 관찰 가능한 동작, 실제 도구와 한계를 설명합니다. KUMA는 YAML front matter와
Production Use Scenario, Behaviors to Test, Known Limitations or Prohibited Behaviors
섹션을 요구합니다. 전략 그룹은 현재 SDK 카탈로그에서 선택합니다.

가능한 확장이 아닌 현재 기능을 쓰세요. 검색 전용 Agent는 계산을 설명할 수 있지만 샘플러 실행이나
파일 저장은 할 수 없습니다. 기능이나 입력이 부족할 때 어떻게 대응해야 하는지 명시하세요.
Profile은 평가 지침이며 도구를 추가하거나 시스템 프롬프트 및 저장된 Case를 변경하지 않습니다.

### `evaluation/` — 선택적 보조 파일

Profile이 schema나 fixture를 참조할 때만 필요합니다. 필수 디렉터리가 아니며 input-contract.json도
필수가 아닙니다. 현재 공식 KUMA 생성 경로는 텍스트를 받습니다. 구조화 schema가 로컬에서 유효해도
원격 지원을 입증하지는 않습니다. 네이티브 매핑은 agent.toml과 binding이 담당합니다.

### 레지스트리와 자동 기록

단위 디렉터리 밖의 resources/registry.toml에 경로, 활성화 여부, adapting/ready와 case 수를 저장합니다.
생성 완료 시 adapting으로 등록하고 인증이 승격을 제어합니다. run은 활성화된 ready Agent를 선택합니다.

다운로더는 재사용을 위해 저장소와 revision을 기록하는 **source-manifest.json을 자동 생성**합니다.
ABB 내부 기록이며 KUMA 필수 파일이나 사용자가 준비할 문서가 아닙니다. 추가 절차를 이어갈 때 유지하세요.

생성 기록은 별도의 `cache/onboarding/<unit-name>-<path-digest>/`에 있습니다.
build-state.json이 재사용 가능한 작업을 추적하고 각 attempt에 계획, SDK 카탈로그, steps,
build-result.json을 저장합니다. 이것들도 자동 기록이며 Agent 소스가 아닙니다.

## 4. 실행 전 검토와 정적 검증

**확인 — 설정 완료:** 성공 메시지만 보지 말고 모든 파일을 검토하세요. 소스 출처와 다음 경계를 확인합니다.

- descriptor는 원본 graph를 가리켜야 합니다. 원본에 `langgraph.json`이 없으면
  `abb-langgraph.json` 같은 최소 descriptor 추가를 출처 기록에 명시하고 graph를 수정하지 않습니다.
- binding은 동기식 무인자 factory에서 실제 Agent를 호출하고 `config`/callbacks, 예외,
  원시 출력을 유지합니다. UI의 메시지 추가/active-agent 수명을 따르고 Case를 격리하며 close 시
  상태를 정리합니다. 전역 가변 대화 상태를 쓰거나 오류를 숨기지 마세요.
- 출력 필드는 실제 답변을 추출하고 증거에는 전체 상태를 보존합니다. 텍스트에서 사실대로
  제공할 수 없는 여러 필수 업무 필드가 있으면 중단합니다.
- 호환 Python으로 원본 lockfile을 설치하고 호스트 ABB 의존성과 분리합니다. uv의 project,
  lockfile, 실행 interpreter를 일치시키세요. 별도 `/opt/venv`로 읽기 전용 소스에 설치하는 것을
  피하고 실행 Python의 pip도 확인합니다.
- 추가 라우트와 binding/runtime COPY를 포함한 **SDK overlay 적용 후 설정**을 확인합니다.
  외부 TOML 검증만으로는 부족합니다.
- profile에는 실제 도구, 호출자가 제공할 데이터, 불가능한 작업을 씁니다. 현재 KUMA 생성은
  `input_type: text`, 정확한 영문 세 제목, 카탈로그의 전략 그룹이 필요합니다. 구현되지 않은
  탐색, 업로드, 코드 실행, 파일 영속화를 능력으로 선언하지 마세요.

수동 수정 후에는 온보딩이 사용하는 정적 validator를 실행합니다.

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
unit = Path("resources/agents/NN-name")
print(validate_unit(unit, plugin))
PY
```

파일과 설치된 SDK parser를 오프라인으로 검사합니다. Agent를 실행하지 않으며 카탈로그 context를
넘기지 않으면 실시간 조회/전략 검증도 하지 않습니다. 생성은 저장한 최신 스냅샷으로 검증하고
KUMA 실행 전 서비스 규칙을 다시 확인합니다. 정적 성공은 실행 성공이 아닙니다. 복잡한 binding은
실제 adapter 경계, 세션 격리, config 전달, 지원 시 async, 예외를 오프라인으로 테스트하세요.
fixture는 자체 완결적이어야 하며 선택적 unit 부재 시 명시적으로 skip해야 합니다.

## 5. local 스모크 Case 하나 실행

설정된 텍스트 Agent를 작게 시작합니다.

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

실제 Docker Agent와 모델 interception을 사용하며 고정 텍스트 Case 및 local Judge로 평가합니다.
Docker와 모델 설정이 필요하고 모델 토큰 비용이 발생할 수 있습니다. KUMA 인증 정보/크레딧은
필요 없지만 인증 정보 없는 오프라인 echo demo와는 다릅니다. 고정 Case는 profile에서 생성되지
않으며 기사 처리나 전문가 handoff를 검증하지 못할 수도 있습니다.

**확인 — local:** Suite 경로, 상세 실행 디렉터리, 답변, trace 상태, Judge 보고서를 보존합니다.
실행 성공과 호스트 수락을 확인해야 실행 가능한 통합이라고 보고할 수 있습니다. 첫 실행 후에는
실패했더라도 view를 확인합니다(7절). import 검사나 fixture 테스트는 실제 실행을 대체하지 않습니다.

일반 Case에 필수 문맥이 없다면 승인 후 실제 네이티브 입력으로 `observe`를 사용할 수 있습니다.
텍스트 binding의 `native-input.json`은 JSON 문자열이며 다른 binding은 실제 schema에 맞춥니다.
본문 없이 “제공된 글을 읽어라”라고만 쓰지 말고 실제 기사나 업무 데이터를 제공하세요.

```bash
python -m agentbench observe AGENT_ID --input native-input.json
```

observe는 KUMA Case/Judge 없이 실행을 기록하지만 모델/도구 비용은 발생할 수 있습니다.
특정 관찰로 실패한 benchmark를 통과로 바꿀 수는 없습니다. 사용자가 바로 KUMA를 요청하면
정적 검토 후 6절로 진행하고 생략한 local 검증은 미실행으로 보고하세요.

## 6. 새로운 KUMA 평가 실행

배포 profile과 현재 전략을 검토하고 KUMA/모델 이용 및 증거 제출 승인을 확인한 뒤 한 Case를 실행합니다.

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

local 통과는 KUMA 호환성 증명이 아닙니다. profile 변경은 미래 Case에만 영향을 줍니다.
생성 Case가 필수 데이터를 제공하는지, 실제 지원하는 작업을 요구하는지 확인하세요. Case 결함과
Agent 문제를 함께 기록하고 통과를 만들기 위해 원본 입력, 출력, Judge 증거를 편집하지 마세요.

동일 실행의 생성, Agent 호출, 제출, Judge polling을 추적합니다. 비동기 접수는 판정이 아니며
기다리는 동안 중복 평가를 시작하지 않습니다. timeout/오류 후에는 저장된 완료/복구 상태를
확인하고 재개 또는 재시도를 결정합니다. 재실행 안전성과 도구 부작용을 존중하며 안전 플래그를
바꿔 복구를 강제하지 마세요. 새 `evaluate`는 새 Suite와 보통 새 Case를 생성하므로 이전 Case의
통제된 재실행이 아닙니다.

## 7. view를 열고 결과 구분

첫 local 실행 후, KUMA 후, 실패 진단·재시도·완료 보고 전에 뷰어를 엽니다. headless 환경에서는
같은 JSON/trace 파일을 검토하고 UI 검토를 하지 못했다고 명시합니다.

```bash
python -m agentbench view results/suites/ACTUAL_SUITE_ID/events.json
```

명령이 출력한 정확한 `Result saved` / `Open later` 경로를 사용합니다. 오프라인 demo는
타임스탬프가 있는 `OFFLINE_RESULT`를 출력합니다. 파일명을 추측하거나 예전 Suite를 쓰지 마세요.
경로까지 포함한 전체 `View:` URL을 열고 서버를 유지하며 끝나면 Ctrl+C로 종료합니다.
`--no-view`여도 결과는 저장됩니다.

**Suite → Case → 각 입력/답변 → 모델/도구/handoff trace → Judge와 증거 →
실행/정리/호스트 수락** 순서로 확인합니다. handoff 성공은 전문가 작업 완료가 아니며,
쓰기를 했다는 문장만으로 실제 쓰기가 입증되지는 않습니다.

| 증거 | 해석과 다음 행동 |
| --- | --- |
| 실행 성공 + 호스트 수락 + Judge pass | 이 Case 통과. 범위를 기록하고 모든 능력으로 일반화하지 않습니다. |
| 실행 성공 + 호스트 수락 + Judge issue | 통합은 실행됐습니다. 행동 문제를 보존하고 통과 목적으로 prompt를 바꾸지 않습니다. |
| 네이티브 예외 / execution failed | Judge가 와도 실행 성공이 아닙니다. 승격 전에 진단합니다. |
| 부분 trace / insufficient evidence / 호스트 거부 | 증거 부족을 별도 보고합니다. OTel complete가 모든 도구 내용 기록을 뜻하지는 않습니다. |
| 기사/데이터 부재 또는 불가능한 Case 작업 | Case/profile 한계를 기록하고 근거 있는 Agent 주장은 별도 판단합니다. 데이터를 만들어내지 않습니다. |

`results/observe/<run-id>/`에서 존재하는 `run.json`, `evaluation/case.json`,
`evaluation/inputs/`, `evaluation/manifest.json`, `evaluation/judge/report.json`을 확인합니다.
파일 부재는 해당 단계가 끝나지 않았음을 나타낼 수 있으므로 판정을 가정하지 마세요. 비정상 종료
코드는 crash가 아니라 Judge issue 때문일 수 있습니다. JSON export만으로 완전한 trace의
독립적인 아카이브가 되지는 않습니다.

## 8. 인증 필요 여부 결정

`evaluate`는 레지스트리를 승격하거나 Case 수를 바꾸지 않습니다. 목표에 `run`의 선택 대상이
되는 것이 포함되면 레지스트리 수량과 추가 실행 승인을 확인한 뒤 실행합니다.

```bash
python -m agentbench certify AGENT_ID --sdk kuma --no-view
```

certify는 설정된 수량을 실행하며 이전 평가 증거를 승인하는 명령이 아닙니다. 모든 Case가 호출
오류 없이 완료되면 Judge 문제가 있어도 `adapting`에서 `ready`로 승격할 수 있습니다. 이미 ready면
재실행 없이 반환하므로 후속 변경은 evaluate로 검증합니다. 실행 문제를 숨기기 위해 ready를 수동
설정하지 마세요. 사용자가 성공적인 평가로 추가 완료를 인정했다면 실제 상태를 보고하고 멈춥니다.
표시만 바꾸려고 추가 유료 인증을 하지 마세요.

## 9. 실패한 경계에서 진단

첫 실패와 저장 증거에서 시작하고 가능하면 최소 오프라인 재현을 만듭니다. graph/binding,
단일/복수 도구 호출, sync/async, 고정 의존성/호스트 환경 중 한 번에 한 요소만 바꿉니다.
진단 스크립트는 배포 unit 밖에 둡니다. 배포 수정과 원본 행동 변경을 구분하고 후자는 별도로
제안하세요. interception을 끄거나 오류를 숨기거나 도구 성공 결과를 만들어내지 마세요.

| 증상 | 확인, 조치, 중단 조건 |
| --- | --- |
| agentbench 부재 또는 다른 checkout import | 현재 venv와 `python -m agentbench`를 쓰고 Agent 수정 전 editable 설치를 확인합니다. |
| Docker 불가, 권한, 이미지 아키텍처 | 같은 사용자의 `docker info`와 플랫폼 확인. 필요한 권한을 얻되 격리는 유지합니다. |
| SDK는 발견됐지만 onboarding hook 또는 kuma import 부재 | 발견은 능력/의존성 검증이 아닙니다. 생성 지원 SDK와 고정 requirements를 사용합니다. |
| catalog/auth/network 실패 | 키 존재, shell 우선순위, endpoint, 네트워크를 비밀 출력 없이 점검하고 해결 전 생성을 중단합니다. |
| 구조화 출력 거부, needs_input, 충돌 | plan/step 기록을 보고 적합 모델, 사실 기반 답변, 검토된 파일 수정을 적용하며 영향받은 단계만 재시도합니다. |
| uv project/lock 불일치, pip 부재, container import 실패 | Python 범위, lock 위치, interpreter, 의존성 격리, COPY 확인. 정적 성공은 설치 증명이 아닙니다. |
| 외부 TOML은 정상이나 overlay 실패 | 빈 `tool_routes = []`와 추가 `[[llm_interception.tool_routes]]`의 충돌을 확인하고 불필요한 빈 선언만 제거합니다. 필수 라우트/interception은 유지합니다. |
| 복수 handoff에서 INVALID_CHAT_HISTORY | AI tool-call ID와 ToolMessage를 대조하고 원 graph를 오프라인 재현합니다. 단일 성공은 병렬 성공을 보장하지 않습니다. |
| Judge가 복구 부재나 외부 작업 주장을 지적 | 모델이 앞선 오류를 받았는지, 도구가 존재/실행됐는지 확인합니다. 문장, 실행 상태, 증거 한계를 구분합니다. |
| 뷰어 공백, 접근 불가, 이전 결과 | web/dist 빌드, 정확한 URL/파일, 서버 유지, 포트 권한을 확인합니다. 뷰어를 고치려고 유료 평가를 재실행하지 않습니다. |

Article Explainer에서는 local 대화가 동작했고, 한 KUMA 실행은 원본 병렬 handoff 오류로 실패했으며
다른 실행은 완료됐지만 행동 문제가 나왔습니다. Case에 기사 본문도 없었습니다. 이는 진단 사례이지
다른 revision/모델/Case의 결과를 보장하지 않습니다. 전략 ID도 카탈로그 검토 없이 재사용하지 마세요.

## 10. 인계 체크리스트와 완료 보고

소스/revision, unit 경로, 생성/수동 수정 파일, 명령, 실제 결과/view 경로를 보고합니다.
local/KUMA 실행, 호스트 수락, Judge를 구분하고 미검증 능력, 알려진 실패, registry 및 Git 상태
(로컬만, commit/push/PR)를 기록하세요. 코드/docs를 `.venv`, 비밀, 이미지, cache, lock,
결과와 구분하고 비밀은 commit하지 마세요.

합의한 온보딩 목표를 증거로 확인하면 중단합니다. 행동 문제는 유효한 benchmark 결과이며
반드시 통합 미완료를 뜻하지는 않습니다. 운 좋게 통과할 때까지 반복하거나 대상 Agent를 몰래
고치지 마세요. commit/PR 요청은 별도 승인 단계로 처리하고 검토 가능한 diff를 준비합니다.

참고: [문제 해결(영문)](../Troubleshooting.md), [알려진 문제(영문)](../Documentation-Issue-Audit.md),
[생성기 구현(영문)](../../agentbench/onboarding/build_agent_env/README.md).

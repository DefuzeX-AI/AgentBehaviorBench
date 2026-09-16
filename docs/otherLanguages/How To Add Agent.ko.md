# Agent 추가

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | [简体中文](How%20To%20Add%20Agent.zh-CN.md) | [繁體中文](How%20To%20Add%20Agent.zh-TW.md) | 한국어

**환경 설정 → 추가 명령 실행 → 생성된 파일 확인** 순서로 진행합니다. 사용자와 coding agent
모두 같은 절차를 따를 수 있습니다. 디렉터리를 바꾸는 명령이 없으면 ABB 저장소 루트에서 실행하세요.

## 1. 환경 설정

### ABB와 호스트 의존성 설치

먼저 [ABB 설치](README.ko.md)를 완료하세요. Git, Python 3.10+, 활성화된 가상 환경이 필요하며,
인증에는 현재 사용자가 접근할 수 있는 Docker가 필요합니다. 선택한 SDK의 호스트 검증 의존성을 설치합니다.

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

sdk list에 kuma가 표시되어야 하며 ABB를 실행하는 사용자로 docker info가 성공해야 합니다.
다운로드와 설정 생성만 할 때는 Docker가 필요 없지만 -c 인증에는 필요합니다.
호스트 SDK와 평가 컨테이너 내부 SDK는 별도로 설치됩니다.

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

key 발급 링크는 [설정 가이드(영어)](../../README.md#configure-a-real-evaluation)에 있습니다.
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

## 2. 추가 명령 실행

URL을 Agent의 GitHub 저장소 주소로 바꾸세요. 파일이나 /tree/branch 페이지 주소는 사용하지 않습니다.

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

- `-b`: 통합 파일을 생성하고 검증한 뒤 adapting으로 등록합니다. Docker 이미지를 즉시 빌드한다는 뜻은 아닙니다.
- `-c`: 인증 절차로 Agent를 빌드하고 실행합니다. 설정된 Case의 실행 검증이 성공하면 ready가 되며,
  Judge는 여전히 행동 문제를 보고할 수 있습니다.

ABB는 소스를 다운로드하고 통합을 계획하며 파일별 검증 결과를 저장한 후 인증 여부를 묻습니다.
생성과 인증에는 요금이 발생할 수 있습니다. 현재 자동 설정은 **LangGraph**를 지원하며 다른 프레임워크는
해당 어댑터 지원이 먼저 필요합니다.

인증 전에 생성 파일을 확인하려면 -c를 생략하세요.

```bash
agentbench agent add https://github.com/owner/repository -b
```

두 옵션을 모두 생략한 agentbench agent add URL은 다운로드와 설정 파일 목록 출력만 수행합니다.
통합 설정을 생성하거나 실행 가능한 Agent를 등록하지 않습니다. 다운로더는 기본 브랜치의 revision을
기록하며 현재 --revision 옵션은 없습니다.

| 옵션 | 용도 |
| --- | --- |
| `--no-view` | 뷰어 없이 인증하며 결과는 저장합니다. |
| `--build-model MODEL` | 통합 파일 생성 모델. |
| `--model MODEL` | 인증 중 Agent가 사용하는 모델. |
| `--answers answers.txt` | 이전 계획의 질문에 텍스트 파일로 답변. |
| `--with-observe` | -b와 함께 observe의 네이티브 입력 프롬프트 생성. |
| `--build-settings settings.toml` | [build] 테이블로 생성 설정 재정의. |

생성 모델 우선순위는 --build-model, 설정 파일의 model, OPENROUTER_BUILD_MODEL,
OPENROUTER_MODEL입니다. 예산, 제한 시간, 재시도를 바꾸기 전에
[기본 설정](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)을 확인하세요.

## 3. 파일별 역할 확인

Agent 단위는 `resources/agents/NN-name/`에 위치합니다. 다운로드한 소스 주변에 통합 파일이 생성되므로
명령을 실행하기 전에 모든 파일을 직접 만들 필요는 없습니다.

```text
resources/agents/NN-name/
├── agent/                   # Downloaded upstream source
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — Agent 자체 소스

다운로드한 원본 저장소가 들어 있습니다. 실제 그래프, 추론과 도구 구현은 여기에 유지합니다.
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

## 생성 이후

-b만 사용했다면 binding과 일치하는 네이티브 입력 JSON을 준비하고 실행을 확인한 뒤 인증합니다.

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

생성된 Agent ID를 사용하세요. observe는 KUMA Case/Judge를 호출하지 않지만 모델/도구 요금은 발생할 수
있습니다. evaluate --cases 1은 레지스트리 수를 바꾸지 않으며 certify는 그 수를 사용하므로 먼저 확인하세요.
이미 ready인 Agent는 재인증 없이 반환합니다. 이후 변경은 evaluate로 검증하세요.

생성이 중단되면 build-result.json과 실패한 단계를 읽고 수정한 뒤 같은 -b 명령을 다시 실행합니다.
완성된 파일은 보존하고 재검증합니다. 수동 파일 충돌은 덮어쓰지 않고 중단합니다.
계획에 추가 정보가 필요하면 --answers answers.txt를 사용하세요.

[문제 해결(영어)](../Troubleshooting.md), [알려진 문제(영어)](../Documentation-Issue-Audit.md),
[개발자 가이드(영어)](../../agentbench/onboarding/build_agent_env/README.md)를 참고하세요.

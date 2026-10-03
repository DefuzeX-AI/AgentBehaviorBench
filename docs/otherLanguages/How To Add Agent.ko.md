# Agent 추가

[English](../How%20To%20Add%20Agent.md) | [Français](How%20To%20Add%20Agent.fr.md) | [日本語](How%20To%20Add%20Agent.ja.md) | [中文](How%20To%20Add%20Agent.zh-CN.md) | 한국어

[ABB 시작 방법 — 영어](../Guide.md) · [CLI 문서](cli.ko.md) · [등록부](Registry.ko.md)

ABB 저장소 루트에서 가상 환경을 활성화한 후 환경 설정, 소스 가져오기, 통합 파일 생성, 검토, Agent 테스트 순서로 진행하세요. SOURCE, AGENT_ID, NN-name과 결과 경로를 실제 값으로 바꾸세요.

## 1. 환경 설정

Git과 Python 3.10+를 설치하고 위 시작 가이드에 따라 ABB를 설치하세요. Agent 실행 및 인증에는 현재 사용자가 접근할 수 있는 Docker가 필요합니다. KUMA 생성 또는 검증 시 ABB와 같은 가상 환경에 KUMA를 설치하세요.

```bash
python -m pip install -e .
python -m pip install "kuma-defuzex[otel]>=0.3.3"
git --version
agentbench --help
agentbench sdk list
docker info
```

`sdk list`는 플러그인 목록이며 의존성 설치를 검증하지 않습니다. 소스 가져오기와 설정 생성에는 Docker가 필요하지 않습니다. 호스트와 컨테이너 SDK 설치는 별개입니다.

`.env`가 없을 때만 `.env.example`을 복사한 후 로컬에서 편집하세요. KUMA는 KUMA_API_KEY(또는 DEFUZEX_API_KEY)를 사용합니다. 설정 생성에는 OpenRouter와 엄격한 구조화 출력을 지원하는 모델이 필요합니다.

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate generation model:
# OPENROUTER_BUILD_MODEL=
```

대상 Agent 실행 모델은 별도로 설정합니다. LangGraph는 OpenRouter, DeepSeek 또는 GLM을 사용할 수 있고 네이티브 ACP는 Agent가 선언한 서비스 인증 정보를 사용합니다. 시작 가이드를 참조하세요. `--build-model`은 생성 모델, `--model`은 인증 시 ABB 대체 대상 모델입니다. 셸 변수가 `.env`보다 우선하며 키를 소스나 생성 파일에 넣지 마세요.

웹 뷰어에는 npm과 Node.js 20.x의 20.19 이상 또는 22.12 이상이 필요합니다. 프런트엔드를 빌드하세요. `--no-view` 평가는 Node나 `web/dist`가 필요하지 않습니다.

```bash
cd web
npm ci
npm run build
cd ..
```

## 2. 소스 가져오기 및 설정 생성

SOURCE는 파일·브랜치 페이지가 아닌 HTTPS GitHub 저장소 URL 또는 로컬 절대 디렉터리입니다. GitHub 기본 브랜치를 가져오며 `--revision` 옵션은 없습니다. 로컬은 `.git`을 제외하고 내용 해시를 기록합니다. 먼저 소스를 가져오세요.

```bash
agentbench agent add https://github.com/owner/repository
```

같은 소스로 통합 파일을 생성하세요. `-b` 또는 `-c` 없이 일반 가져오기를 반복하면 중복 오류가 발생합니다. 해당 옵션은 기존 단위를 재사용하지만 수정된 소스에서 갱신하지 않습니다. 로컬은 `/absolute/path/to/local-agent`, PowerShell은 `"C:\work\local-agent"`을 사용할 수 있습니다.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma
```

`-b`는 LangGraph와 ACP를 지원하며 파일 생성·검증 후 `adapting`으로 등록합니다. Docker는 빌드하지 않습니다. KUMA는 계획 전에 현재 전략 목록을 가져옵니다. 기본 `local`에는 통합 검증 인터페이스가 없으므로 생성에는 KUMA를 사용하세요. 추가 정보가 필요하면 실제 배포 답변을 UTF-8 `answers.txt`에 쓰고 `--answers answers.txt`로 반복하세요. 실패 후 완료된 유효한 파일은 유지되므로 재시도 전에 `build-result.json`을 확인하세요.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma --answers answers.txt
```

## 3. 파일별 역할

Agent 단위는 `resources/agents/NN-name/`에 위치합니다. 가져온 소스 주변에 통합 파일이 생성되므로
명령을 실행하기 전에 모든 파일을 직접 만들 필요는 없습니다.

```text
resources/agents/NN-name/
├── agent/                   # 가져온 업스트림 또는 로컬 소스 스냅샷
├── agent.toml               # ABB execution configuration
├── bindings/                # LangGraph binding; not required for native ACP
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

### `bindings/*.py`

LangGraph binding은 인수 없는 동기 팩토리로 실제 Agent를 반환하며 입출력 변환과 종료 처리를 담당합니다. ACP는 `agent.toml`에 설정된 네이티브 명령과 프로토콜을 사용하며 Python binding 팩토리가 필수는 아닙니다. Agent 자체 동작을 유지하세요.

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

## 4. 설정 검토 및 검증

실제 소스에 맞춰 진입점, 입출력 매핑, 의존성, 인증 정보 선언 및 모델·도구 경로를 검토하세요. LangGraph는 graph descriptor와 팩토리, ACP는 네이티브 명령과 세션을 확인하세요. Profile에는 실제 도구, 필수 입력 데이터와 제한을 작성하세요. 수동 수정 후 검증하세요(Bash 예제).

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/NN-name"), plugin))
PY
```

파일과 SDK 파서를 검사하며 Agent를 실행하지 않습니다. 목록 컨텍스트를 전달하지 않으면 현재 원격 전략 목록을 검증하지 않습니다. 정적 검증 통과는 실행 성공을 의미하지 않습니다.

## 5. local 스모크 Case 실행

등록부에서 새 Agent를 `enabled = true`로 설정하고 Case 하나를 실행하세요. `local`은 일반 텍스트 Cases와 로컬 Judge를 사용하며 KUMA 백엔드 크레딧을 쓰지 않습니다. Agent와 Judge는 유료 모델을 호출할 수 있습니다. 통합 인증이나 KUMA 행동 평가 결과는 아닙니다.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

## 6. KUMA로 평가

스모크 테스트 후 KUMA로 새 Case를 생성하고 실행 증거와 Judge 보고서를 수집하세요. 설정된 모델 서비스 및 KUMA API를 호출합니다.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

## 7. 결과 확인

`Result saved`의 실제 파일 경로를 사용하고 전체 `View:` URL을 열어 명령을 유지하세요. Conversation은 입출력, Judge는 발견 문제, Timing은 실행 및 OTel을 보여줍니다. 실행 완료와 판정은 별개입니다. `issue`는 발견 사항이며 `insufficient_evidence` 자체는 확인된 결함이 아닙니다.

```bash
agentbench view results/suites/SUITE_ID/events.json
```

## 8. 통합 인증

`adapting` Agent를 `run` 대상으로 만들려면 활성 상태에서 인증하세요. 등록부 Case 예산에 따라 새로 실행하며 이전 결과를 승인하는 작업이 아닙니다. 모든 Cases가 호출 오류 없이 완료되면 Judge 발견 사항이 있어도 `ready`가 됩니다. 이미 ready이면 재실행하지 않으므로 이후 테스트에는 `evaluate`를 쓰세요. `agent add -c`는 유효한 통합 파일이 필요하며 `-b`를 암묵적으로 활성화하지 않습니다.

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
```

## 9. 결과, 재실행 및 문제 해결

계획, Cases 및 이벤트는 `results/suites/SUITE_ID/`, 실행 상세는 보통 `results/observe/RUN_ID/`에 저장됩니다. 출력된 경로를 사용하세요. `--results-dir DIR`은 ABB 결과 루트이며 `evaluate --output DIR`은 SDK 산출물을 별도로 선택합니다.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view --results-dir results/my-run
```

`resume`은 복구 가능한 미완료 작업을 계속하고 `retry`는 미완료 Case 하나를 대상으로 합니다. `reuse`는 저장 입력을 새로 실행·판정하며 원본 결과를 유지합니다. 번호는 1부터입니다. 뷰어의 Rerun this Case 및 Open reuse Suite도 사용할 수 있습니다. 배치 소유 프로세스를 유지하세요. 안전하지 않거나 응답이 불확실한 요청은 복구되지 않을 수 있습니다.

```bash
agentbench resume results/suites/SUITE_ID
agentbench retry results/suites/SUITE_ID --agent AGENT_ID --case 1
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 1
```

Export JSON은 스냅샷이며 전체 추적 또는 독립 HTML 보고서가 아닙니다. 전체 증거를 위해 Suite와 참조 실행 디렉터리를 유지하세요. `agentbench clean --dry-run`으로 미리 보고 실제 보관 전에 실행과 뷰어를 중지하세요.

Trace UI not built이면 `web/`를 빌드하세요. Docker 오류는 같은 사용자로 `docker info`, SDK 가져오기 오류는 ABB 가상 환경의 SDK 설치를 확인하세요. 모델·키 오류는 서비스, 모델명 및 셸 우선순위를 확인하세요. 계획 오류나 needs_input은 저장 기록을 확인하고 실제 정보를 보완하세요.

[CLI 문서](cli.ko.md) · [상세 문제 해결 — 영어](../Troubleshooting.md)

# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — 워크플로를 검토하는 알파카 Agent" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文简体</a> |
  <a href="README.zh-TW.md">中文繁體</a> |
  한국어
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **ABB를 실행하기 전에:** Python 3.10 이상, 실행 중인 Docker Desktop 또는 Docker
> Engine, 결과 뷰어 빌드에 쓰는 Node.js 20.19 이상 또는 22.12 이상을 준비하세요. KUMA는
> 평가 컨테이너 빌드 시 PyPI에서 자동으로 설치됩니다. 포함된 두 Agent 모두
> `KUMA_API_KEY`(또는 `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
> `TAVILY_API_KEY`가 필요합니다.

AgentBehaviorBench는 등록된 AI Agent를 격리된 런타임에서 실행하고 실행 증거를 수집한
뒤, 선택 가능한 SDK로 결과를 평가합니다. 기본 SDK는 내장 KUMA adapter입니다. 결과는
로컬에 저장되며 ABB 브라우저 뷰어에서 확인할 수 있습니다.

![AgentBehaviorBench 실행 아키텍처](../figures/framework.png)

처음 실행할 때 오류가 나면 먼저 아래 [문제 해결](#문제-해결)을 확인하세요.

## 빠른 시작

저장소 루트에서 가상 환경을 만들고 ABB를 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

결과 뷰어는 `web/`에서 빌드하며, 빌드 결과물은 저장소에 포함되지 않습니다. 결과를 열기 전에
한 번 빌드하세요. `run`, `evaluate`, `certify`는 실행 후 뷰어를 시작하고,
`agentbench view`는 저장된 결과를 다시 엽니다.

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
```

로컬 환경 파일을 만들고 자격 증명을 입력합니다.

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

`KUMA_API_KEY`는 KUMA SDK 문서가 사용하는 변수 이름입니다. ABB는 별칭
`DEFUZEX_API_KEY`도 받지만, `KUMA_API_KEY`가 비어 있을 때만 사용합니다.
`OPENROUTER_MODEL`은 필수이며 기본값이 없습니다. 위 값은 예시이므로 계정에서 사용할 수
있는 모델로 바꾸세요.

Docker를 시작합니다(`docker info`가 성공해야 합니다). 저장소의 registry에는 두 Agent가
활성화되어 있고 모두 `ready`입니다: `react-agent`와 `company-research-agent`. 먼저 Case
하나를 평가하세요. 키에 과금되는 KUMA Case 및 Judge 서비스를 호출합니다.

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

registry에서 `enabled = true`이고 상태가 `ready`인 모든 Agent를 실행합니다.

```bash
agentbench run
```

ABB는 선택된 Agent의 확인을 요청하고, `results/`에 결과 스냅샷을 저장한 뒤 로컬
뷰어를 시작합니다. 헤드리스 또는 자동 실행에는 다음을 사용하세요.

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

## 요구 사항 및 환경 변수

| 요구 사항 | 용도 |
| --- | --- |
| Python 3.10 이상 | ABB 호스트 CLI와 harness. |
| Docker Desktop / Docker Engine | 포함된 ready Agent는 Docker 컨테이너에서 실행됩니다. `run`, `evaluate`, `certify`, `observe` 전에 Docker를 시작해야 합니다. |
| Node.js 20.19 이상 또는 22.12 이상(npm 포함) | `web/` 결과 뷰어를 한 번 빌드합니다. 헤드리스 실행(`--no-view`)에는 필요 없습니다. |
| `KUMA_API_KEY` 또는 `DEFUZEX_API_KEY` | 기본 KUMA SDK의 Case 및 Judge 접근 권한. 둘 다 설정하면 `KUMA_API_KEY`를 사용합니다. |
| `OPENROUTER_API_KEY` | Docker Agent의 모델 트래픽은 ABB interceptor를 거쳐 OpenRouter로 전달됩니다. |
| `OPENROUTER_MODEL` | 필수 모델 이름. `.env.example`의 값은 예시일 뿐 실행 시 기본값이 아닙니다. 계정에서 사용할 수 있는 모델을 고르세요. |
| `TAVILY_API_KEY` | 포함된 두 Agent(ReAct, Company Research)의 웹 검색 자격 증명. |

`.env`는 Git에서 무시됩니다. Shell에 이미 export된 변수는 `.env` 값을 덮어쓰며,
`--env-file PATH`는 다른 dotenv 파일을 선택하고, `--model MODEL`은 한 번의 명령에만
모델을 덮어씁니다.

선택적 OpenRouter 설정:

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

설치된 버전의 도움말은 `agentbench --help` 또는 `agentbench <command> --help`로 확인할
수 있습니다. 이것이 전체 인수 레퍼런스입니다.

| 명령 | 용도 |
| --- | --- |
| `agentbench run` | 활성화되고 `ready`인 모든 Agent를 평가합니다. 기본 명령입니다. |
| `agentbench evaluate company-research-agent --cases 1` | 선택한 수의 독립 Case로 하나의 Agent를 평가합니다. |
| `agentbench observe company-research-agent` | 네이티브 입력으로 Agent를 실행하고 trace를 저장합니다. Case를 만들거나 Judge를 호출하지 않습니다. |
| `agentbench certify NEW-AGENT` | `adapting` Agent를 인증하고 성공하면 `ready`로 승격합니다. |
| `agentbench view RESULT.json` | 저장된 결과를 로컬 뷰어에서 다시 엽니다. 경로는 실행이 끝날 때 `Result saved:` 뒤에 출력되는 타임스탬프가 붙은 파일입니다(먼저 `web/`를 빌드하세요. 빠른 시작 참조). |
| `agentbench sdk list` | SDK adapter 디렉터리를 구현을 import하지 않고 나열합니다. |
| `agentbench clean --dry-run` | `clean`이 `cache/history-trash/`로 옮길 `results/` 아래의 참조되지 않는 항목을 표시합니다. 아무것도 삭제하지 않습니다. |

자주 쓰는 `run` 옵션:

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

Agent 추가(`agent add`)는 [영어 README의 CLI 절](../../README.md#cli)(영어)과
[agent onboarding guide](../How%20To%20Add%20Agent.md)(영어)를 참조하세요.

## 문제 해결

처음 실행할 때 `evaluate`, `run`, `certify`가 출력하는 주요 오류입니다. 모델 이름 행을
제외하면 모두 KUMA 요청 전에 멈추므로 과금되지 않습니다.

| 출력 | 원인 | 해결 |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker가 실행 중이 아니거나 `DOCKER_HOST`가 존재하지 않는 daemon을 가리킵니다. | `docker info`가 성공할 때까지 Docker Desktop 또는 Docker 서비스를 시작합니다. |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | 환경 변수와 `.env` 어디에도 KUMA 자격 증명이 없습니다. | `.env`에 `KUMA_API_KEY`를 설정합니다. |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | 변수에 KUMA 키가 아닌 값(예: OpenRouter 키)이 들어 있습니다. | KUMA용으로 발급된 `dfx_` 키를 사용합니다. |
| `AuthenticationError: Invalid API key.`(직전에 `GET defuzex.ai/… \| HTTP 401`) | KUMA 키가 잘못되었거나, 폐기되었거나, 다른 Backend용입니다. | 키를 교체합니다. `KUMA_BASE_URL`을 설정했다면 함께 확인합니다. |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | `OPENROUTER_MODEL`이 설정되지 않았습니다. ABB에는 기본 모델이 없습니다. | `.env`에 `OPENROUTER_MODEL`을 설정하거나 `--model`을 전달합니다. |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY`(또는 `TAVILY_API_KEY`) | 모델 업스트림이나 Agent의 `agent.toml`이 요구하는 자격 증명이 없습니다. | 표시된 변수를 `.env`에 추가하거나 export합니다. |
| `LLM call 01 \| openrouter \| FAILED` 뒤에 업스트림 메시지를 인용한 `related network: upstream_error POST …` | 모델 업스트림이 호출을 거부했습니다(존재하지 않는 모델 이름, 키 권한 없음 등). Case는 이미 생성되었으므로 Judge와 과금이 발생할 수 있습니다. | 사용 중인 키로 업스트림이 제공하는 모델 이름을 사용합니다. |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | 이 체크아웃에서 뷰어를 아직 빌드하지 않았습니다. | Node.js 20.19 이상 또는 22.12 이상으로 표시된 명령을 실행합니다. |

`agentbench clean`은 아무것도 삭제하지 않습니다. `results/` 바로 아래의 참조되지 않는 항목을
보여 주고, 확인 후 `cache/history-trash/<타임스탬프>/`로 옮깁니다. 저장된 Suite와 그것이
참조하는 산출물은 그대로 남습니다. 되돌리려면 실행과 뷰어를 멈춘 뒤 보관된 항목을
`results/`로 다시 옮기세요.

## 저장소 구성

```text
AgentBehaviorBench/
├── resources/registry.toml
├── resources/agents/
├── agentbench/cli/
├── agentbench/harness/
├── agentbench/runtime/
├── agentbench/sdk/plugin/kuma/
├── web/
└── results/
```

- `resources/registry.toml`은 Agent, 상태, runtime을 선언합니다.
- `resources/agents/`는 각 Agent 단위와 ABB 설정을 포함합니다.
- `agentbench/cli/`는 터미널 명령을 제공합니다.
- `agentbench/harness/`는 suite 실행, 결과, registry 로드를 담당합니다.
- `agentbench/runtime/`은 로컬 또는 Docker에서 Agent를 실행합니다.
- `agentbench/sdk/plugin/`는 내장 SDK adapter와 디렉터리 탐색을 포함합니다.
- `web/`은 결과 뷰어의 소스입니다. `npm run build`가 CLI가 제공하는 `web/dist`를 만듭니다.

실행 흐름은 `resources/registry.toml` → CLI 선택 → SuiteRunner / 평가 SDK →
Agent adapter와 런타임 → 결과 스냅샷과 로컬 뷰어입니다(위 아키텍처 그림 참조).

## 개발

```bash
python -m pytest
```

저장소 규칙은 [AGENTS.md](../../AGENTS.md)(영어)를 참조하세요.

## 라이선스

MIT. 자세한 내용은 [LICENSE](../../LICENSE)를 참조하세요.

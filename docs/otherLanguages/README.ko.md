# AgentBehaviorBench (ABB)

> 브라우저 UI 빌드에는 Node.js 20.19+ (20.x) 또는 22.12+ 및 npm이 필요합니다. `web/`에서 `npm ci`, `npm run build`를 실행한 후 `agentbench view`를 사용하세요. `--no-view` 실행에는 빌드가 필요 없습니다. 최신 설치·인증·제약 사항은 [기본 가이드(영어)](../../README.md)를 참고하세요.

<p align="center">
  <img alt="AgentBehaviorBench — 워크플로를 검토하는 알파카 Agent" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文</a> |
  한국어
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **ABB를 실행하기 전에:** Python 3.10 이상, 실행 중인 Docker Desktop 또는 Docker
> Engine을 준비하세요. KUMA는 평가 컨테이너 빌드 시 PyPI에서 자동으로 설치됩니다. Company Research
> Agent에는 `KUMA_API_KEY`(또는 `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`,
> `OPENROUTER_MODEL`, `TAVILY_API_KEY`가 필요합니다.

AgentBehaviorBench는 등록된 AI Agent를 격리된 런타임에서 실행하고 실행 증거를 수집한
뒤, 선택 가능한 SDK로 결과를 평가합니다. 기본 SDK는 내장 KUMA adapter입니다. 결과는
로컬에 저장되며 ABB 브라우저 뷰어에서 확인할 수 있습니다.

![AgentBehaviorBench 실행 아키텍처](../figures/framework.png)

## 빠른 시작

저장소 루트에서 가상 환경을 만들고 ABB를 설치합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
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

Docker를 시작한 뒤 registry에서 `enabled = true`이고 상태가 `ready`인 모든 Agent를
실행합니다.

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
| `KUMA_API_KEY` 또는 `DEFUZEX_API_KEY` | 기본 KUMA SDK의 Case 및 Judge 접근 권한. |
| `OPENROUTER_API_KEY` | Docker Agent의 모델 트래픽은 ABB interceptor를 거쳐 OpenRouter로 전달됩니다. |
| `OPENROUTER_MODEL` | 실행에 사용할 모델 이름. |
| `TAVILY_API_KEY` | 포함된 Company Research Agent의 웹 검색 자격 증명. |

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
수 있습니다.

| 명령 | 용도 |
| --- | --- |
| `agentbench run` | 활성화되고 `ready`인 모든 Agent를 평가합니다. 기본 명령입니다. |
| `agentbench evaluate company-research-agent --cases 1` | 선택한 수의 독립 Case로 하나의 Agent를 평가합니다. |
| `agentbench observe company-research-agent` | 네이티브 입력으로 Agent를 실행하고 trace를 저장합니다. Case를 만들거나 Judge를 호출하지 않습니다. |
| `agentbench certify react-agent` | `adapting` Agent를 인증하고 성공하면 `ready`로 승격합니다. |
| `agentbench view results/benchmark.json` | 저장된 결과를 로컬 뷰어에서 다시 엽니다. |
| `agentbench sdk list` | 내장 및 설치된 평가 SDK를 나열합니다. |
| `agentbench clean --dry-run` | 복구 가능한 아카이브로 이동될 로컬 결과 기록을 표시합니다. |

자주 쓰는 `run` 옵션:

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

전체 인수는 영어 [CLI reference](../../README.md#cli-and-repository-layout)를, Agent 추가는
[Agent 추가 가이드](How%20To%20Add%20Agent.ko.md)를 참조하세요.

## 저장소 구성

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

- `resources/registry.toml`은 Agent, 상태, runtime을 선언합니다.
- `resources/agents/`는 각 Agent 단위와 ABB 설정을 포함합니다.
- `agentbench/cli/`는 터미널 명령을 제공합니다.
- `agentbench/harness/`는 suite 실행, 결과, registry 로드를 담당합니다.
- `agentbench/runtime/`은 로컬 또는 Docker에서 Agent를 실행합니다.
- `agentbench/sdk/plugin/`는 내장 SDK adapter와 플러그인 탐색을 포함합니다.

## 개발

```bash
python -m pytest
```

저장소 규칙은 [AGENTS.md](../../AGENTS.md) 및 [docs/AGENTS.md](../../AGENTS.md)를
참조하세요.

## 라이선스

MIT. 자세한 내용은 [LICENSE](../../LICENSE)를 참조하세요.

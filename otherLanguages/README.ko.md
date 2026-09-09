# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench (ABB)"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  <a href="../README.md">English</a> |
  <a href="README.fr.md">Français</a> |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文简体</a> |
  <a href="README.zh-TW.md">中文繁體</a> |
  한국어
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## 소식

- AgentBehaviorBench (ABB)는 이제 DefuzeX SDK의 `get_input()` / `submit()` handshake를 통해 등록된 LangGraph Agent를 실행합니다.

## 개요

AgentBehaviorBench (ABB)는 대상 Agent를 호출하고, 그 출력과 실행 trace를 수집하며, 요청된 workflow를 올바르게 완료했는지 판단해야 하는 end-to-end 작업에서 AI Agent를 평가하기 위한 benchmark입니다.

등록된 Agent와 benchmark Case가 주어지면, AgentBehaviorBench (ABB)는 신뢰할 수 있는 host harness를 통해 해당 Agent를 실행합니다. 이 harness는 framework-specific 또는 containerized Agent를 시작하고, credential-safe Model Interceptor를 통해 model traffic을 routing하며, 각 SDK input과 Agent response를 원자적으로 갱신되는 JSON events로 기록하고, 완료된 run을 DefuzeX Judge에 제출할 수 있습니다.

AgentBehaviorBench (ABB)는 Agent 평가를 재현 가능하게 만들도록 설계되었습니다. Agent는 registry에 선언되고, LangGraph 같은 framework adapter를 통해 적응되며, `adapting`에서 `ready`로 인증됩니다. 인증이 성공한 뒤에만 기본 benchmark run에 포함됩니다.

현재 실행 흐름은 다음과 같습니다:

```text
registry.toml
-> SuiteRunner
-> BenchmarkRunner
-> DefuzeX SDK Run
-> Agent Adapter / Runtime
-> Judge Report
```

이 repository에는 다음이 포함됩니다:

- `agentbench/cli`: terminal entry point와 progress output.
- `agentbench/harness`: SDK handshake, suite execution, results, registry.
- `agentbench/adapter`: framework-neutral adapter contract와 LangGraph support.
- `agentbench/runtime`: local 및 Docker runtime integration.
- `resources/agents`: 재현 가능한 benchmark agent fixtures.
- `services/model-interceptor`: Docker runs에서 model provider access를 위한 투명 interceptor.

![AgentBehaviorBench (ABB) framework](../figures/framework.png)

## 설정

AgentBehaviorBench (ABB)에는 Python 3.10 이상과 DefuzeX Python SDK가 필요합니다. SDK는 AgentBehaviorBench (ABB)가 사용하는 benchmark protocol을 제공합니다. 즉 benchmark requirements를 parse하고, DefuzeX Cases를 만들고, 각 SDK input을 drive하며, evidence를 기록하고, 완료된 runs를 judging을 위해 제출합니다.

이 repository를 포함하는 parent workspace에서 virtual environment를 만들고 활성화합니다:

```powershell
cd <workspace-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

AgentBehaviorBench (ABB)를 editable mode로 설치합니다:

```powershell
python -m pip install -e .\defuzeX_AgentBench
```

### 내부 SDK 빌드

이 repository는 현재 내부 DefuzeX SDK `dev` branch에 의존합니다. SDK가 일반 package installation용으로 배포되기 전까지, `Defuze-SDK`가 아직 local에 clone되어 있지 않다면 SDK `dev` branch(`https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev`)에서 `defuzeX_AgentBench` 옆에 clone한 뒤 같은 `.venv`에 설치합니다:

```powershell
cd <workspace-root>
git clone --branch dev --single-branch https://github.com/DefuzeX-AI/Defuze-SDK
python -m pip install -e .\Defuze-SDK
python -m pip install -e .\defuzeX_AgentBench
```

일반적인 source checkout은 `Defuze-SDK`와 `defuzeX_AgentBench`를 같은 parent workspace 아래의 sibling directories로 두고, 둘 다 editable mode로 설치합니다.

> [!NOTE]
> PAT는 Personal Access Token을 뜻합니다. 내부 DefuzeX SDK repository가 private이면 GitHub가 HTTPS clone 시 PAT를 요구할 수 있습니다. PAT는 password처럼 다루세요. source files, README examples, notebooks, commit된 `.env` files에 넣지 마세요.

## 사용법

AgentBehaviorBench (ABB)를 설치한 뒤 benchmark workspace에서 launcher script로 시작합니다:

```powershell
cd <workspace-root>
.\.venv\Scripts\Activate.ps1
python .\run_agentbench.py
```

AgentBehaviorBench (ABB) repository에서 package를 직접 실행할 수도 있습니다:

```powershell
cd <workspace-root>\defuzeX_AgentBench
python -m agentbench
```

run을 저장하고 local result viewer에서 live benchmark events를 확인하려면 output path를 전달합니다:

```powershell
python -m agentbench --output results\result.json
```

`--output`이 없으면 AgentBehaviorBench (ABB)는 terminal에서 실행되고 JSON result artifact를 만들지 않습니다. `--output`을 사용하면 AgentBehaviorBench (ABB)는 원자적으로 갱신되는 JSON result file을 쓰고 local viewer를 시작하므로 benchmark가 실행되는 동안 events를 새로고침하고 확인할 수 있습니다.

official Case 또는 Judge providers를 사용할 때는 DefuzeX API key를 설정합니다:

```powershell
$env:DEFUZEX_API_KEY = "dfx_<public-id>.<secret>"
```

test suite를 실행합니다:

```powershell
python -m pytest
```

Agent-facing instructions는 [AGENTS.md](../AGENTS.md)에서 시작하세요. 더 긴 documentation guide는 [docs/AGENTS.md](../docs/AGENTS.md)에 있습니다.

## 테스트할 Agent 추가 방법

자신의 Agent를 benchmark에 추가하려면 agent에게 [docs/How To Add Agent.md](../docs/How%20To%20Add%20Agent.md)를 읽고 그 문서의 onboarding flow를 따르게 하세요.

AgentBehaviorBench (ABB)는 external Agent project를 repeatable benchmark target으로 바꾸는 데 필요한 요소를 제공합니다. registry-based discovery, framework adapters, Docker runtime support, Model Interceptor를 통한 model credential routing, 원자적으로 갱신되는 result artifacts, local result viewing, 그리고 `adapting`에서 `ready`로의 certification입니다. 이를 통해 동일한 DefuzeX Cases에서 Agent들을 일관되게 비교하면서 runtime behavior, outputs, judgment evidence를 inspectable하게 유지할 수 있습니다.

## 인용 및 라이선스

MIT License. [LICENSE](../LICENSE)를 참조하세요.

저희 작업이 도움이 되었다면 다음과 같이 인용해 주세요:
